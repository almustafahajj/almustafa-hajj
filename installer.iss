; ملف إعداد مُثبِّت برنامج موسم الحج (Inno Setup 6)
; يبني مُثبِّتاً واحداً: Output\HajjApp-Setup.exe
; يغلّف ناتج PyInstaller من: dist\HajjApp
;
; البناء:  ابنِ الـexe أولاً (بناء نسخة exe.bat) ثم شغّل "بناء المُثبِّت.bat"
; أو يدوياً:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss

#define AppName "برنامج موسم الحج"
#define AppNameEn "HajjApp"
#define AppVersion "1.0.0"
#define AppPublisher "المصطفى للحج والعمرة"
#define AppExe "HajjApp.exe"

[Setup]
AppId={{A7C1E4B2-9D3F-4A6E-B8C2-0A1B2C3D4E5F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
; التثبيت لكل المستخدمين في Program Files (يتطلّب صلاحية المسؤول)
DefaultDirName={autopf}\{#AppNameEn}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=HajjApp-Setup
SetupIconFile=hajj_app\assets\logo.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
; Inno يشحن الإنجليزية افتراضياً؛ نصوص الأزرار تكفي، وعناويننا عربية
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "إنشاء اختصار على سطح المكتب"; GroupDescription: "اختصارات:"
Name: "webicon"; Description: "اختصار نسخة الويب (فتح من المتصفّح)"; GroupDescription: "اختصارات:"; Flags: unchecked

[Files]
; كل ناتج PyInstaller (الـexe + مجلد _internal بكل مكتباته)
Source: "dist\HajjApp\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\HajjApp\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} — نسخة الويب"; Filename: "{app}\{#AppExe}"; Parameters: "web"
Name: "{group}\إلغاء تثبيت {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{autodesktop}\{#AppName} — ويب"; Filename: "{app}\{#AppExe}"; Parameters: "web"; Tasks: webicon

[Run]
; تشغيل البرنامج مباشرة بعد انتهاء التثبيت (اختياري)
Filename: "{app}\{#AppExe}"; Description: "تشغيل {#AppName} الآن"; Flags: nowait postinstall skipifsilent

; ملاحظة: بيانات المستخدم (كشف الحجّاج والحسابات) تُحفظ في
;   %LOCALAPPDATA%\HajjApp\data
; ولا تُحذف عند إلغاء التثبيت — حفاظاً على البيانات.
