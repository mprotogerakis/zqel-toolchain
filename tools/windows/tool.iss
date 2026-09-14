; Der gemeinsame Installer fuer unsere Windows-Werkzeugpakete.
;
; Aufruf (setzt win_package.ps1 zusammen):
;   iscc /DToolName=Gappa /DToolVersion=1.4.0 /DToolId={{...}} \
;        /DBaseName=gappa-1.4.0-win_amd64 /DStageDir=<pfad> /DOutDir=<pfad> tool.iss
;
; Er installiert ALLES aus StageDir, rekursiv. Das ist Absicht: was im Paket
; liegt, hat win_package.ps1 dort hingelegt und gegen den Pin geprueft - eine
; zweite Dateiliste hier waere eine zweite Autoritaet, und sie wuerde genau die
; Datei vergessen, auf die es ankommt.
;
; Mit installiert werden deshalb NICHT nur die Binaerdateien:
;   licenses\      die vollstaendigen Lizenztexte - die des Werkzeugs aus seinem
;                  Quellbaum, die der Bibliotheken aus genau den MSYS2-Paketen,
;                  aus denen die DLLs stammen.
;   NOTICE.txt     welche Bibliothek unter welcher Lizenz mitfaehrt.
;   SOURCES.txt    wo der uebersetzte Quellcode herkommt, Paket fuer Paket.
; Ein Lizenzhinweis ohne den Text daneben ist eine Behauptung, keine Auflage.
;
; Die Werkzeuge liegen dynamisch gelinkt vor, die DLLs daneben. Auch das ist
; Absicht: die LGPL verlangt, dass sich die Bibliothek austauschen laesst.

#ifndef ToolName
  #error ToolName muss per /D gesetzt werden
#endif
#ifndef ToolVersion
  #error ToolVersion muss per /D gesetzt werden
#endif
#ifndef ToolId
  #error ToolId muss per /D gesetzt werden - je Werkzeug eine feste GUID
#endif
#ifndef StageDir
  #error StageDir muss per /D gesetzt werden
#endif
#ifndef BaseName
  #error BaseName muss per /D gesetzt werden
#endif
#ifndef OutDir
  #define OutDir "."
#endif

[Setup]
AppId={#ToolId}
AppName={#ToolName}
AppVersion={#ToolVersion}
AppPublisher=zqel (Hochschule Duesseldorf)
DefaultDirName={autopf}\{#ToolName}
DefaultGroupName={#ToolName}
DisableProgramGroupPage=yes
LicenseFile={#StageDir}\COPYING
OutputDir={#OutDir}
OutputBaseFilename={#BaseName}-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesEnvironment=yes
WizardStyle=modern
UninstallDisplayName={#ToolName} {#ToolVersion}

[Languages]
Name: "deutsch"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "addtopath"; Description: "{#ToolName} in den PATH aufnehmen (zqel findet es dann selbst)"; GroupDescription: "Einbindung:"

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; \
    Tasks: addtopath; Check: NotAlreadyOnPath(ExpandConstant('{app}'))

[Code]
function NotAlreadyOnPath(Dir: string): Boolean;
var
  Existing: string;
begin
  Result := True;
  if RegQueryStringValue(HKLM, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
                         'Path', Existing) then
    Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Existing) + ';') = 0;
end;
