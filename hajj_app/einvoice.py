"""الفاتورة الإلكترونية الإماراتية بصيغة PEPPOL — UBL 2.1 / PINT AE.

النموذج الإماراتي للفوترة الإلكترونية يقوم على تبادل مستند **XML مُهيكل**
(بمواصفة PINT AE المبنية على UBL 2.1) عبر شبكة PEPPOL من خلال مزوّدي خدمة
معتمدين — لا على رمز QR كما في النموذج السعودي. هذه الوحدة تبني ملف الفاتورة
الإلكترونية الرسمي (XML) بالحقول الأساسية المطلوبة.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from .fields import parse_amount, vat_breakdown

# معرّفات تخصيص الفوترة الإماراتية على PEPPOL
PINT_AE_CUSTOMIZATION = "urn:peppol:pint:billing-1@ae-1"
PINT_AE_PROFILE = "urn:peppol:bis:billing"

_NS_UBL = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
_NS_CAC = ("urn:oasis:names:specification:ubl:schema:xsd:"
           "CommonAggregateComponents-2")
_NS_CBC = ("urn:oasis:names:specification:ubl:schema:xsd:"
           "CommonBasicComponents-2")


def _iso_date(value: str) -> str:
    """يضمن تاريخاً بصيغة YYYY-MM-DD (يتراجع لتاريخ اليوم إن تعذّر)."""
    s = (value or "").strip()
    return s if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else date.today().isoformat()


def invoice_amounts(rec, *, vat_mode: str = "inclusive"):
    """يعيد (صافي، ضريبة، إجمالي) للفاتورة من قيمة البرنامج."""
    gross = parse_amount(rec.program_value)
    if gross is None:
        gross = parse_amount(rec.paid_amount)
    return vat_breakdown(float(gross or 0.0), mode=vat_mode)


def build_ubl_invoice(rec, *, company=None, number: str = "INV-0001",
                      date_str: str = "", item_desc: str = "",
                      vat_mode: str = "inclusive", currency: str = "AED",
                      vat_rate: int = 5) -> str:
    """يبني فاتورة إلكترونية بصيغة UBL 2.1 (PINT AE) كنصّ XML."""
    from .pdf_io import build_invoice_item, company_info

    co = company_info(company)
    if not item_desc:
        item_desc = build_invoice_item(rec)
    net, vat, total = invoice_amounts(rec, vat_mode=vat_mode)
    issue = _iso_date(date_str)
    customer = rec.full_name_ar or rec.full_name_en or "—"

    e = escape
    cur = currency

    def m(v) -> str:
        return f"{float(v):.2f}"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="{_NS_UBL}" xmlns:cac="{_NS_CAC}" xmlns:cbc="{_NS_CBC}">
  <cbc:CustomizationID>{PINT_AE_CUSTOMIZATION}</cbc:CustomizationID>
  <cbc:ProfileID>{PINT_AE_PROFILE}</cbc:ProfileID>
  <cbc:ID>{e(number)}</cbc:ID>
  <cbc:IssueDate>{issue}</cbc:IssueDate>
  <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>{cur}</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyName><cbc:Name>{e(co["name_ar"])}</cbc:Name></cac:PartyName>
      <cac:PostalAddress>
        <cbc:StreetName>{e(co["address"])}</cbc:StreetName>
        <cac:Country><cbc:IdentificationCode>AE</cbc:IdentificationCode></cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme>
        <cbc:CompanyID>{e(co["trn"])}</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:PartyTaxScheme>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>{e(co["name_ar"])}</cbc:RegistrationName>
        <cbc:CompanyID>{e(co["trn"])}</cbc:CompanyID>
      </cac:PartyLegalEntity>
      <cac:Contact><cbc:Telephone>{e(co["phone"])}</cbc:Telephone></cac:Contact>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyName><cbc:Name>{e(customer)}</cbc:Name></cac:PartyName>
      <cac:PostalAddress>
        <cac:Country><cbc:IdentificationCode>AE</cbc:IdentificationCode></cac:Country>
      </cac:PostalAddress>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>{e(customer)}</cbc:RegistrationName>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="{cur}">{m(vat)}</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="{cur}">{m(net)}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="{cur}">{m(vat)}</cbc:TaxAmount>
      <cac:TaxCategory>
        <cbc:ID>S</cbc:ID>
        <cbc:Percent>{vat_rate}</cbc:Percent>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="{cur}">{m(net)}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="{cur}">{m(net)}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="{cur}">{m(total)}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="{cur}">{m(total)}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:InvoicedQuantity unitCode="C62">1</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="{cur}">{m(net)}</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Name>{e(item_desc)}</cbc:Name>
      <cac:ClassifiedTaxCategory>
        <cbc:ID>S</cbc:ID>
        <cbc:Percent>{vat_rate}</cbc:Percent>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:ClassifiedTaxCategory>
    </cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="{cur}">{m(net)}</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
</Invoice>
"""


def export_invoice_xml(rec, path: str | Path, **kw) -> Path:
    """يكتب ملف الفاتورة الإلكترونية (UBL 2.1 / PINT AE) إلى المسار."""
    path = Path(path)
    path.write_text(build_ubl_invoice(rec, **kw), encoding="utf-8")
    return path
