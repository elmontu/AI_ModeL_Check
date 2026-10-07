@echo off
setlocal
title Model Release Assurance Demo
set "MRA_DEMO_INSTALLER_FILE=%~f0"
powershell.exe -NoLogo -NoProfile -Command "$text=[IO.File]::ReadAllText($env:MRA_DEMO_INSTALLER_FILE);$marker='# MRA POWERSHELL PAYLOAD';$offset=$text.LastIndexOf($marker);if($offset -lt 0){throw 'Installer payload missing'};& ([scriptblock]::Create($text.Substring($offset+$marker.Length)))"
set "MRA_DEMO_EXIT_CODE=%ERRORLEVEL%"
if not "%MRA_DEMO_NO_PAUSE%"=="1" pause
exit /b %MRA_DEMO_EXIT_CODE%
# MRA POWERSHELL PAYLOAD
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
# Use Windows PowerShell's own modules even when launched from another PowerShell version.
$env:PSModulePath = Join-Path $PSHOME 'Modules'

# Reviewed immutable downloads. Update this launcher to adopt another snapshot.
$DemoRevision = '76d5efe71a853f24da90fab2d15c141b0ac82157'
$SourceHash = 'f5070bd4962215d4cabbe6f10596e7044c1ddf8eecbc212965451545bcb18ae1'
$PythonVersion = '3.13.16'
$PythonHash = '95fad176338f1d6a799e45946488063f4aa61764e6cff2f132ddeffbf7a04c34'
$DataProbeBase64 = 'IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJQcm92aXNpb24gYW5kIHZlcmlmeSBmb3VyIHBhY2thZ2UtbG9jYWwgcHVibGljIGRlbW8gZGF0YXNldHMuCgpObyBuZXR3b3JrIHJlcXVlc3QsIG1vZGVsIHRyYWluaW5nLCByZXNlYXJjaC1jb3JwdXMgZG93bmxvYWQgb3Igc291cmNlLWRpcmVjdG9yeQptdXRhdGlvbiBpcyBwZXJmb3JtZWQuIEV4aXN0aW5nIHBhcnRpYWwgb3IgbW9kaWZpZWQgY2FjaGVzIGFyZSBuZXZlciByZXBsYWNlZC4KIiIiCmZyb20gX19mdXR1cmVfXyBpbXBvcnQgYW5ub3RhdGlvbnMKCmltcG9ydCBhcmdwYXJzZQppbXBvcnQgaGFzaGxpYgppbXBvcnQgaW8KaW1wb3J0IGpzb24KZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCmltcG9ydCBzdGF0CmZyb20gdHlwaW5nIGltcG9ydCBBbnkKClNLTEVBUk5fVkVSU0lPTiA9ICIxLjYuMSIKU0NIRU1BID0gIm1yYS1kZW1vLWRhdGFzZXRzL3YxIgpNQU5JRkVTVCA9ICJtYW5pZmVzdC5qc29uIgpQUk9GSUxFUyA9ICgKICAgICgic2tsZWFybi13aW5lIiwgImxvYWRfd2luZSIsIDE3OCwgMTMsICJjbGFzc2lmaWNhdGlvbiIpLAogICAgKCJza2xlYXJuLWJyZWFzdC1jYW5jZXIiLCAibG9hZF9icmVhc3RfY2FuY2VyIiwgNTY5LCAzMCwgImNsYXNzaWZpY2F0aW9uIiksCiAgICAoInNrbGVhcm4tZGlnaXRzIiwgImxvYWRfZGlnaXRzIiwgMTc5NywgNjQsICJjbGFzc2lmaWNhdGlvbiIpLAogICAgKCJza2xlYXJuLWRpYWJldGVzIiwgImxvYWRfZGlhYmV0ZXMiLCA0NDIsIDEwLCAicmVncmVzc2lvbiIpLAopCk1BWF9GSUxFX0JZVEVTID0gNCAqIDEwMjQgKiAxMDI0Ck1BWF9NQU5JRkVTVF9CWVRFUyA9IDEyOCAqIDEwMjQKCgpjbGFzcyBEZW1vRGF0YUVycm9yKFZhbHVlRXJyb3IpOgogICAgIiIiVGhlIGZpeGVkIHB1YmxpYyBkYXRhc2V0IGNhY2hlIGNhbm5vdCBiZSBjcmVhdGVkIG9yIHNhZmVseSByZXBsYXllZC4iIiIKCgpkZWYgX3JlcXVpcmUoY29uZGl0aW9uOiBib29sLCBtZXNzYWdlOiBzdHIpIC0+IE5vbmU6CiAgICBpZiBub3QgY29uZGl0aW9uOgogICAgICAgIHJhaXNlIERlbW9EYXRhRXJyb3IobWVzc2FnZSkKCgpkZWYgX2Nhbm9uaWNhbCh2YWx1ZTogQW55KSAtPiBieXRlczoKICAgIHJldHVybiBqc29uLmR1bXBzKHZhbHVlLCBzb3J0X2tleXM9VHJ1ZSwgc2VwYXJhdG9ycz0oIiwiLCAiOiIpLCBlbnN1cmVfYXNjaWk9VHJ1ZSwKICAgICAgICAgICAgICAgICAgICAgIGFsbG93X25hbj1GYWxzZSkuZW5jb2RlKCJ1dGYtOCIpICsgYiJcbiIKCgpkZWYgX3NoYShjb250ZW50OiBieXRlcykgLT4gc3RyOgogICAgcmV0dXJuIGhhc2hsaWIuc2hhMjU2KGNvbnRlbnQpLmhleGRpZ2VzdCgpCgoKZGVmIF9vcmRpbmFyeV9kaXJlY3RvcnkocGF0aDogUGF0aCkgLT4gTm9uZToKICAgIGluZm8gPSBwYXRoLmxzdGF0KCkKICAgIF9yZXF1aXJlKHN0YXQuU19JU0RJUihpbmZvLnN0X21vZGUpIGFuZCBub3Qgc3RhdC5TX0lTTE5LKGluZm8uc3RfbW9kZSkKICAgICAgICAgICAgIGFuZCBub3QgZ2V0YXR0cihpbmZvLCAic3RfZmlsZV9hdHRyaWJ1dGVzIiwgMCkgJiAweDQwMCwKICAgICAgICAgICAgICJEYXRhc2V0IGRpcmVjdG9yaWVzIG11c3QgYmUgb3JkaW5hcnkgbG9jYWwgZGlyZWN0b3JpZXMiKQoKCmRlZiBfcm9vdChvdXRwdXQ6IFBhdGgsICosIGNyZWF0ZTogYm9vbCkgLT4gUGF0aDoKICAgIHBhdGggPSBQYXRoKG91dHB1dCkKICAgIF9yZXF1aXJlKHBhdGguaXNfYWJzb2x1dGUoKSBhbmQgIi4uIiBub3QgaW4gcGF0aC5wYXJ0cwogICAgICAgICAgICAgYW5kIG5vdCBzdHIocGF0aCkuc3RhcnRzd2l0aCgoIi8vIiwgIlxcXFwiKSksCiAgICAgICAgICAgICAiLS1vdXRwdXQgbXVzdCBiZSBhbiBhYnNvbHV0ZSBvcmRpbmFyeSBsb2NhbCBwYXRoIikKICAgIGZvciBwYXJlbnQgaW4gcmV2ZXJzZWQoKHBhdGgsICpwYXRoLnBhcmVudHMpKToKICAgICAgICBpZiBwYXJlbnQuZXhpc3RzKCkgb3IgcGFyZW50LmlzX3N5bWxpbmsoKToKICAgICAgICAgICAgX29yZGluYXJ5X2RpcmVjdG9yeShwYXJlbnQpCiAgICBpZiBub3QgcGF0aC5leGlzdHMoKToKICAgICAgICBfcmVxdWlyZShjcmVhdGUsICJEYXRhc2V0IGNhY2hlIGRpcmVjdG9yeSBpcyBtaXNzaW5nIikKICAgICAgICBwYXRoLm1rZGlyKHBhcmVudHM9VHJ1ZSwgZXhpc3Rfb2s9RmFsc2UpCiAgICBfb3JkaW5hcnlfZGlyZWN0b3J5KHBhdGgpCiAgICByZXR1cm4gcGF0aAoKCmRlZiBfcmVhZF9maWxlKHBhdGg6IFBhdGgsIG1heGltdW06IGludCkgLT4gYnl0ZXM6CiAgICBpbmZvID0gcGF0aC5sc3RhdCgpCiAgICBfcmVxdWlyZShzdGF0LlNfSVNSRUcoaW5mby5zdF9tb2RlKSBhbmQgbm90IHN0YXQuU19JU0xOSyhpbmZvLnN0X21vZGUpCiAgICAgICAgICAgICBhbmQgbm90IGdldGF0dHIoaW5mbywgInN0X2ZpbGVfYXR0cmlidXRlcyIsIDApICYgMHg0MDAgYW5kIGluZm8uc3RfbmxpbmsgPT0gMSwKICAgICAgICAgICAgICJEYXRhc2V0IGZpbGVzIG11c3QgYmUgb3JkaW5hcnkgc2luZ2xlLWxpbmsgZmlsZXMiKQogICAgX3JlcXVpcmUoMCA8IGluZm8uc3Rfc2l6ZSA8PSBtYXhpbXVtLCAiRGF0YXNldCBmaWxlIGV4Y2VlZHMgaXRzIGZpeGVkIGJvdW5kIikKICAgIGNvbnRlbnQgPSBwYXRoLnJlYWRfYnl0ZXMoKQogICAgX3JlcXVpcmUobGVuKGNvbnRlbnQpID09IGluZm8uc3Rfc2l6ZSwgIkRhdGFzZXQgZmlsZSBjaGFuZ2VkIHdoaWxlIHJlYWRpbmciKQogICAgY3VycmVudCA9IHBhdGgubHN0YXQoKQogICAgX3JlcXVpcmUoKGluZm8uc3RfZGV2LCBpbmZvLnN0X2lubywgaW5mby5zdF9zaXplLCBpbmZvLnN0X210aW1lX25zKSA9PQogICAgICAgICAgICAgKGN1cnJlbnQuc3RfZGV2LCBjdXJyZW50LnN0X2lubywgY3VycmVudC5zdF9zaXplLCBjdXJyZW50LnN0X210aW1lX25zKSwKICAgICAgICAgICAgICJEYXRhc2V0IGZpbGUgY2hhbmdlZCB3aGlsZSByZWFkaW5nIikKICAgIHJldHVybiBjb250ZW50CgoKZGVmIF9leHBlY3RlZCgpIC0+IHR1cGxlW2RpY3Rbc3RyLCBBbnldLCBkaWN0W3N0ciwgYnl0ZXNdLCBkaWN0W3N0ciwgdHVwbGVbQW55LCBBbnldXV06CiAgICBpbXBvcnQgbnVtcHkgYXMgbnAKICAgIGltcG9ydCBza2xlYXJuCiAgICBmcm9tIHNrbGVhcm4gaW1wb3J0IGRhdGFzZXRzCgogICAgX3JlcXVpcmUoc2tsZWFybi5fX3ZlcnNpb25fXyA9PSBTS0xFQVJOX1ZFUlNJT04sCiAgICAgICAgICAgICAiRGVtbyBkYXRhIHJlcXVpcmVzIHNjaWtpdC1sZWFybiAxLjYuMTsgaW5zdGFsbCB0aGUgZGVjbGFyZWQgZGVtbyBydW50aW1lIikKICAgIGVudHJpZXMsIHNlcmlhbGl6ZWQsIGFycmF5cyA9IFtdLCB7fSwge30KICAgIGZvciBkYXRhc2V0X2lkLCBsb2FkZXJfbmFtZSwgcm93cywgZmVhdHVyZXMsIHRhc2sgaW4gUFJPRklMRVM6CiAgICAgICAgZGF0YSA9IGdldGF0dHIoZGF0YXNldHMsIGxvYWRlcl9uYW1lKSgpCiAgICAgICAgeCwgeSA9IG5wLmFzYXJyYXkoZGF0YS5kYXRhKSwgbnAuYXNhcnJheShkYXRhLnRhcmdldCkKICAgICAgICBfcmVxdWlyZSh4Lm5kaW0gPT0gMiBhbmQgeC5zaGFwZSA9PSAocm93cywgZmVhdHVyZXMpCiAgICAgICAgICAgICAgICAgYW5kIHkubmRpbSA9PSAxIGFuZCB5LnNoYXBlID09IChyb3dzLCksCiAgICAgICAgICAgICAgICAgIkJ1bmRsZWQgZGF0YXNldCBzaGFwZSBkaWZmZXJzIGZyb20gaXRzIGRlY2xhcmVkIHByb2ZpbGU6ICIgKyBkYXRhc2V0X2lkKQogICAgICAgIF9yZXF1aXJlKHguZHR5cGUua2luZCBpbiAiaXVmIiBhbmQgeS5kdHlwZS5raW5kIGluICJpdWYiCiAgICAgICAgICAgICAgICAgYW5kIG5wLmlzZmluaXRlKHgpLmFsbCgpIGFuZCBucC5pc2Zpbml0ZSh5KS5hbGwoKSwKICAgICAgICAgICAgICAgICAiQnVuZGxlZCBkYXRhc2V0IGlzIG5vdCBhIGZpbml0ZSBhbGlnbmVkIG51bWVyaWMgbWF0cml4OiAiICsgZGF0YXNldF9pZCkKICAgICAgICBuYW1lcyA9IFtzdHIodmFsdWUpIGZvciB2YWx1ZSBpbiBkYXRhLmZlYXR1cmVfbmFtZXNdCiAgICAgICAgX3JlcXVpcmUobGVuKG5hbWVzKSA9PSBmZWF0dXJlcywgIkJ1bmRsZWQgZmVhdHVyZSBuYW1lcyBkbyBub3QgYWxpZ246ICIgKyBkYXRhc2V0X2lkKQogICAgICAgIHN0cmVhbSA9IGlvLkJ5dGVzSU8oKQogICAgICAgIG5wLnNhdmV6X2NvbXByZXNzZWQoc3RyZWFtLCB4PXgsIHk9eSkKICAgICAgICBjb250ZW50ID0gc3RyZWFtLmdldHZhbHVlKCkKICAgICAgICBfcmVxdWlyZSgwIDwgbGVuKGNvbnRlbnQpIDw9IE1BWF9GSUxFX0JZVEVTLCAiQnVuZGxlZCBzZXJpYWxpemVkIGRhdGFzZXQgZXhjZWVkcyBpdHMgYm91bmQiKQogICAgICAgIGZpbGVuYW1lID0gZGF0YXNldF9pZCArICIubnB6IgogICAgICAgIHNlcmlhbGl6ZWRbZmlsZW5hbWVdID0gY29udGVudAogICAgICAgIGFycmF5c1tmaWxlbmFtZV0gPSAoeCwgeSkKICAgICAgICBkYXRhX2JpbmRpbmcgPSB7ImRhdGFzZXRfaWQiOiBkYXRhc2V0X2lkLCAibG9hZGVyIjogbG9hZGVyX25hbWUsCiAgICAgICAgICAgICAgICAgICAgICAgICJza2xlYXJuX3ZlcnNpb24iOiBTS0xFQVJOX1ZFUlNJT04sICJ4IjogeC50b2xpc3QoKSwgInkiOiB5LnRvbGlzdCgpLAogICAgICAgICAgICAgICAgICAgICAgICAiZmVhdHVyZV9uYW1lcyI6IG5hbWVzfQogICAgICAgIGVudHJpZXMuYXBwZW5kKHsKICAgICAgICAgICAgImRhdGFzZXRfaWQiOiBkYXRhc2V0X2lkLCAibG9hZGVyIjogbG9hZGVyX25hbWUsICJ0YXNrIjogdGFzaywKICAgICAgICAgICAgInJvd3MiOiByb3dzLCAiZmVhdHVyZXMiOiBmZWF0dXJlcywgImZlYXR1cmVfbmFtZXMiOiBuYW1lcywKICAgICAgICAgICAgInNvdXJjZSI6ICJzY2lraXQtbGVhcm4gcGFja2FnZS1sb2NhbCBwdWJsaWMgc2FtcGxlIiwKICAgICAgICAgICAgInNvdXJjZV91cmwiOiAiaHR0cHM6Ly9zY2lraXQtbGVhcm4ub3JnLzEuNi9kYXRhc2V0cy90b3lfZGF0YXNldC5odG1sIiwKICAgICAgICAgICAgImZpbGVuYW1lIjogZmlsZW5hbWUsICJieXRlcyI6IGxlbihjb250ZW50KSwgInNoYTI1NiI6IF9zaGEoY29udGVudCksCiAgICAgICAgICAgICJkYXRhX3NoYTI1NiI6IF9zaGEoX2Nhbm9uaWNhbChkYXRhX2JpbmRpbmcpKSwKICAgICAgICAgICAgInhfZHR5cGUiOiBzdHIoeC5kdHlwZSksICJ5X2R0eXBlIjogc3RyKHkuZHR5cGUpLAogICAgICAgIH0pCiAgICBtYW5pZmVzdCA9IHsKICAgICAgICAic2NoZW1hIjogU0NIRU1BLCAic2tsZWFybl92ZXJzaW9uIjogU0tMRUFSTl9WRVJTSU9OLAogICAgICAgICJudW1weV92ZXJzaW9uIjogbnAuX192ZXJzaW9uX18sICJkYXRhc2V0cyI6IGVudHJpZXMsCiAgICAgICAgInByb3Zpc2lvbmluZyI6ICJjb3BpZXMgb2YgaW5zdGFsbGVkIHBhY2thZ2UtbG9jYWwgcHVibGljIHNhbXBsZXM7IG5vIGV4dGVybmFsIGRhdGFzZXQgZG93bmxvYWQiLAogICAgICAgICJleHRlcm5hbF9kYXRhc2V0X2Rvd25sb2FkcyI6IEZhbHNlLCAicmVzZWFyY2hfZGF0YXNldHNfcHJvdmlzaW9uZWQiOiBGYWxzZSwKICAgICAgICAicHJpdmF0ZV9kYXRhX2FkbWl0dGVkIjogRmFsc2UsICJtb2RlbF90cmFpbmluZ19leGVjdXRlZCI6IEZhbHNlLAogICAgICAgICJsaWNlbnNlX3Njb3BlIjogIlNvdXJjZSBhdHRyaWJ1dGlvbiByZXRhaW5lZDsgbm8gaW5zdGl0dXRpb25hbCBkYXRhLXJpZ2h0cyBhcHByb3ZhbCBpcyBhc3NlcnRlZCIsCiAgICB9CiAgICByZXR1cm4gbWFuaWZlc3QsIHNlcmlhbGl6ZWQsIGFycmF5cwoKCmRlZiBfdmVyaWZ5KHJvb3Q6IFBhdGgsIG1hbmlmZXN0OiBkaWN0W3N0ciwgQW55XSwgc2VyaWFsaXplZDogZGljdFtzdHIsIGJ5dGVzXSwKICAgICAgICAgICAgYXJyYXlzOiBkaWN0W3N0ciwgdHVwbGVbQW55LCBBbnldXSkgLT4gZGljdFtzdHIsIEFueV06CiAgICBpbXBvcnQgbnVtcHkgYXMgbnAKCiAgICBleHBlY3RlZF9uYW1lcyA9IHNldChzZXJpYWxpemVkKSB8IHtNQU5JRkVTVH0KICAgIF9yZXF1aXJlKHtwYXRoLm5hbWUgZm9yIHBhdGggaW4gcm9vdC5pdGVyZGlyKCl9ID09IGV4cGVjdGVkX25hbWVzLAogICAgICAgICAgICAgIkRhdGFzZXQgY2FjaGUgaXMgcGFydGlhbCBvciBjb250YWlucyB1bmV4cGVjdGVkIGZpbGVzOyBjaG9vc2UgYSBmcmVzaCBvdXRwdXQgZGlyZWN0b3J5IikKICAgIGFjdHVhbF9tYW5pZmVzdCA9IF9yZWFkX2ZpbGUocm9vdCAvIE1BTklGRVNULCBNQVhfTUFOSUZFU1RfQllURVMpCiAgICBfcmVxdWlyZShhY3R1YWxfbWFuaWZlc3QgPT0gX2Nhbm9uaWNhbChtYW5pZmVzdCksCiAgICAgICAgICAgICAiRGF0YXNldCBtYW5pZmVzdCBkaWZmZXJzIGZyb20gdGhlIGRlY2xhcmVkIGluc3RhbGxlZCBzYW1wbGVzOyBleGlzdGluZyBmaWxlcyByZXRhaW5lZCIpCiAgICBmb3IgZmlsZW5hbWUsIGV4cGVjdGVkIGluIHNlcmlhbGl6ZWQuaXRlbXMoKToKICAgICAgICBjb250ZW50ID0gX3JlYWRfZmlsZShyb290IC8gZmlsZW5hbWUsIE1BWF9GSUxFX0JZVEVTKQogICAgICAgIF9yZXF1aXJlKF9zaGEoY29udGVudCkgPT0gX3NoYShleHBlY3RlZCkgYW5kIGNvbnRlbnQgPT0gZXhwZWN0ZWQsCiAgICAgICAgICAgICAgICAgIkRhdGFzZXQgZmlsZSBkaWZmZXJzIGZyb20gaXRzIGRlY2xhcmVkIGJ5dGVzOyBleGlzdGluZyBmaWxlcyByZXRhaW5lZDogIiArIGZpbGVuYW1lKQogICAgICAgIHdpdGggbnAubG9hZChpby5CeXRlc0lPKGNvbnRlbnQpLCBhbGxvd19waWNrbGU9RmFsc2UpIGFzIHNhdmVkOgogICAgICAgICAgICBfcmVxdWlyZShzZXQoc2F2ZWQuZmlsZXMpID09IHsieCIsICJ5In0sCiAgICAgICAgICAgICAgICAgICAgICJEYXRhc2V0IGFyY2hpdmUgY29udGFpbnMgdW5leHBlY3RlZCBhcnJheXMiKQogICAgICAgICAgICBleHBlY3RlZF94LCBleHBlY3RlZF95ID0gYXJyYXlzW2ZpbGVuYW1lXQogICAgICAgICAgICBfcmVxdWlyZShzYXZlZFsieCJdLmR0eXBlID09IGV4cGVjdGVkX3guZHR5cGUgYW5kIHNhdmVkWyJ5Il0uZHR5cGUgPT0gZXhwZWN0ZWRfeS5kdHlwZQogICAgICAgICAgICAgICAgICAgICBhbmQgbnAuYXJyYXlfZXF1YWwoc2F2ZWRbIngiXSwgZXhwZWN0ZWRfeCkKICAgICAgICAgICAgICAgICAgICAgYW5kIG5wLmFycmF5X2VxdWFsKHNhdmVkWyJ5Il0sIGV4cGVjdGVkX3kpLAogICAgICAgICAgICAgICAgICAgICAiRGF0YXNldCBhcnJheXMgZGlmZmVyIGZyb20gdGhlaXIgcGFja2FnZS1sb2NhbCBsb2FkZXI6ICIgKyBmaWxlbmFtZSkKICAgIHJldHVybiBtYW5pZmVzdAoKCmRlZiB2ZXJpZnlfZGVtb19kYXRhKG91dHB1dDogUGF0aCkgLT4gZGljdFtzdHIsIEFueV06CiAgICAiIiJSZWFkLW9ubHkgZXhhY3QgcmVwbGF5IG9mIGFuIGV4aXN0aW5nIGNvbXBsZXRlIGZpeGVkIHB1YmxpYyBjYWNoZS4iIiIKICAgIG1hbmlmZXN0LCBzZXJpYWxpemVkLCBhcnJheXMgPSBfZXhwZWN0ZWQoKQogICAgcmV0dXJuIF92ZXJpZnkoX3Jvb3Qob3V0cHV0LCBjcmVhdGU9RmFsc2UpLCBtYW5pZmVzdCwgc2VyaWFsaXplZCwgYXJyYXlzKQoKCmRlZiBwcmVwYXJlX2RlbW9fZGF0YShvdXRwdXQ6IFBhdGgpIC0+IGRpY3Rbc3RyLCBBbnldOgogICAgIiIiQ3JlYXRlIGV4Y2x1c2l2ZWx5IGluIGFuIGVtcHR5IGRpcmVjdG9yeSwgb3IgdmVyaWZ5IHdpdGhvdXQgd3JpdGVzLiIiIgogICAgbWFuaWZlc3QsIHNlcmlhbGl6ZWQsIGFycmF5cyA9IF9leHBlY3RlZCgpCiAgICByb290ID0gX3Jvb3Qob3V0cHV0LCBjcmVhdGU9VHJ1ZSkKICAgIGlmIGFueShyb290Lml0ZXJkaXIoKSk6CiAgICAgICAgcmV0dXJuIF92ZXJpZnkocm9vdCwgbWFuaWZlc3QsIHNlcmlhbGl6ZWQsIGFycmF5cykKICAgIGZvciBmaWxlbmFtZSwgY29udGVudCBpbiBzZXJpYWxpemVkLml0ZW1zKCk6CiAgICAgICAgd2l0aCAocm9vdCAvIGZpbGVuYW1lKS5vcGVuKCJ4YiIpIGFzIGhhbmRsZToKICAgICAgICAgICAgaGFuZGxlLndyaXRlKGNvbnRlbnQpCiAgICAjIFdyaXRlIHRoaXMgY29tcGxldGlvbiByZWNlaXB0IGxhc3QuIEludGVycnVwdGVkIHNldHVwIHN0YXlzIHBhcnRpYWwgYW5kCiAgICAjIGlzIG5ldmVyIHNpbGVudGx5IHJlcGFpcmVkIGJ5IG92ZXJ3cml0aW5nIGZpbGVzIG9uIHRoZSBuZXh0IGF0dGVtcHQuCiAgICB3aXRoIChyb290IC8gTUFOSUZFU1QpLm9wZW4oInhiIikgYXMgaGFuZGxlOgogICAgICAgIGhhbmRsZS53cml0ZShfY2Fub25pY2FsKG1hbmlmZXN0KSkKICAgIHJldHVybiBfdmVyaWZ5KHJvb3QsIG1hbmlmZXN0LCBzZXJpYWxpemVkLCBhcnJheXMpCgoKZGVmIG1haW4oKSAtPiBOb25lOgogICAgcGFyc2VyID0gYXJncGFyc2UuQXJndW1lbnRQYXJzZXIoZGVzY3JpcHRpb249X19kb2NfXykKICAgIHBhcnNlci5hZGRfYXJndW1lbnQoIi0tb3V0cHV0IiwgdHlwZT1QYXRoLCByZXF1aXJlZD1UcnVlLAogICAgICAgICAgICAgICAgICAgICAgICBoZWxwPSJhYnNvbHV0ZSBsb2NhbCBkaXJlY3Rvcnk7IGVtcHR5IGluaXRpYWxseSwgZXhhY3RseSB2ZXJpZmllZCBvbiByZXVzZSIpCiAgICBhcmdzID0gcGFyc2VyLnBhcnNlX2FyZ3MoKQogICAgdHJ5OgogICAgICAgIG1hbmlmZXN0ID0gcHJlcGFyZV9kZW1vX2RhdGEoYXJncy5vdXRwdXQpCiAgICBleGNlcHQgKERlbW9EYXRhRXJyb3IsIE9TRXJyb3IsIFZhbHVlRXJyb3IpIGFzIGV4YzoKICAgICAgICBwYXJzZXIuZXhpdCgyLCAiRGVtbyBkYXRhc2V0IHNldHVwIGZhaWxlZDogIiArIHN0cihleGMpICsgIlxuRXhpc3RpbmcgZmlsZXMgcmV0YWluZWQ7IG5vIHJlcGxhY2VtZW50IG9yIGZhbGxiYWNrLlxuIikKICAgIHByaW50KGpzb24uZHVtcHMoeyJzdGF0dXMiOiAidmVyaWZpZWQiLCAic2NoZW1hIjogU0NIRU1BLAogICAgICAgICAgICAgICAgICAgICAgInNrbGVhcm5fdmVyc2lvbiI6IG1hbmlmZXN0WyJza2xlYXJuX3ZlcnNpb24iXSwKICAgICAgICAgICAgICAgICAgICAgICJkYXRhc2V0cyI6IFt7ImlkIjogZW50cnlbImRhdGFzZXRfaWQiXSwgInJvd3MiOiBlbnRyeVsicm93cyJdLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAiZmVhdHVyZXMiOiBlbnRyeVsiZmVhdHVyZXMiXX0KICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBmb3IgZW50cnkgaW4gbWFuaWZlc3RbImRhdGFzZXRzIl1dLAogICAgICAgICAgICAgICAgICAgICAgImV4dGVybmFsX2RhdGFzZXRfZG93bmxvYWRzIjogRmFsc2V9LCBzb3J0X2tleXM9VHJ1ZSkpCgoKaWYgX19uYW1lX18gPT0gIl9fbWFpbl9fIjoKICAgIG1haW4oKQo='
$DataProbeHash = '2577bee010690c79f0c3fcc533fb250f7460903aa5f4454d9f52bd20ed32eed7'

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-SafeRoot([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -notmatch '^[A-Za-z]:[\\/]') {
        throw 'Choose an absolute local drive path; relative paths and network shares are refused.'
    }
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    $drive = New-Object IO.DriveInfo -ArgumentList ([IO.Path]::GetPathRoot($full))
    if ($drive.DriveType -eq [IO.DriveType]::Network) { throw 'Mapped network drives are refused.' }
    if ($full.Length -le 3 -or $full -match '(?i)(^|[\\/])OneDrive[^\\/]*([\\/]|$)') {
        throw 'The installation must be outside OneDrive and cannot be a drive root.'
    }
    foreach ($syncRoot in @($env:OneDrive, $env:OneDriveConsumer, $env:OneDriveCommercial)) {
        if (-not [string]::IsNullOrWhiteSpace($syncRoot)) {
            $sync = [IO.Path]::GetFullPath($syncRoot).TrimEnd('\', '/')
            if ($full.Equals($sync, [StringComparison]::OrdinalIgnoreCase) -or
                $full.StartsWith($sync + '\', [StringComparison]::OrdinalIgnoreCase)) {
                throw 'The installation must be outside the configured OneDrive folder.'
            }
        }
    }
    $cursor = $full
    while (-not [string]::IsNullOrEmpty($cursor)) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Linked paths are refused: $cursor"
            }
        }
        $parent = [IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) { break }
        $cursor = $parent.FullName
    }
    return $full
}

function Assert-FileHash([string]$Path, [string]$Expected) {
    $null = Assert-SafeRoot $Path
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or (Get-Sha256 $Path) -cne $Expected) {
        throw "File missing or checksum changed: $Path. The installer will not replace it."
    }
}

function Write-NewText([string]$Path, [string]$Text) {
    $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}

function Get-Download([string]$Url, [string]$Path, [string]$Expected) {
    if (Test-Path -LiteralPath $Path) {
        Assert-FileHash $Path $Expected
        Write-Host "Verified cached download: $([IO.Path]::GetFileName($Path))"
        return
    }
    $null = Assert-SafeRoot $Path
    $pending = $Path + '.partial'
    $null = Assert-SafeRoot $pending
    if (Test-Path -LiteralPath $pending) {
        Assert-FileHash $pending $Expected
        Move-Item -LiteralPath $pending -Destination $Path
        Write-Host "Recovered a complete, verified download."
        return
    }
    Write-Host "Downloading $Url"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $client = New-Object Net.WebClient
    try { $client.DownloadFile($Url, $pending) } finally { $client.Dispose() }
    Assert-FileHash $pending $Expected
    $null = Assert-SafeRoot $Path
    Move-Item -LiteralPath $pending -Destination $Path
}

function Expand-VerifiedArchive([string]$Archive, [string]$Target, [string]$Prefix) {
    $targetFull = Assert-SafeRoot $Target
    if (Test-Path -LiteralPath $targetFull) {
        throw "Extraction target already exists: $targetFull. Existing or partial files are never overwritten."
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    $entries = New-Object 'System.Collections.Generic.List[object]'
    $names = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    [long]$total = 0
    try {
        if ($zip.Entries.Count -gt 20000) { throw 'Archive contains too many entries.' }
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName
            if ($name.Contains('\') -or $name.Contains(':') -or $name.StartsWith('/') -or
                $name -match '(^|/)\.\.?(/|$)' -or $name.Contains([char]0)) {
                throw "Unsafe archive path: $name"
            }
            if (-not [string]::IsNullOrEmpty($Prefix)) {
                if (-not $name.StartsWith($Prefix, [StringComparison]::Ordinal)) { throw 'Unexpected archive root.' }
                $name = $name.Substring($Prefix.Length)
            }
            if ($name -eq '') { continue }
            $relative = $name.TrimEnd('/')
            if (-not $names.Add($relative)) { throw "Duplicate archive path: $relative" }
            $unixType = ($entry.ExternalAttributes -shr 16) -band 0xF000
            if ($unixType -eq 0xA000 -or ($entry.ExternalAttributes -band 0x400) -ne 0) {
                throw 'Archive links are refused.'
            }
            $total += $entry.Length
            if ($entry.Length -gt 67108864 -or $total -gt 536870912) { throw 'Archive exceeds extraction limits.' }
            $destination = [IO.Path]::GetFullPath((Join-Path $targetFull $relative))
            if (-not $destination.StartsWith($targetFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Archive path escapes the target.'
            }
            $entries.Add(@{ Entry = $entry; Path = $destination; Directory = $name.EndsWith('/') })
        }
        $null = New-Item -ItemType Directory -Path $targetFull
        foreach ($record in $entries) {
            if ($record.Directory) {
                $null = [IO.Directory]::CreateDirectory($record.Path)
            } else {
                $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($record.Path))
                $input = $record.Entry.Open()
                $output = [IO.File]::Open($record.Path, [IO.FileMode]::CreateNew)
                try { $input.CopyTo($output) } finally { $output.Dispose(); $input.Dispose() }
            }
        }
    } finally { $zip.Dispose() }
}

function Save-Inventory([string]$Directory, [string]$Receipt, [string]$Kind, [string]$Version) {
    $root = Assert-SafeRoot $Directory
    $files = @()
    foreach ($item in (Get-ChildItem -LiteralPath $root -Recurse -Force -File | Sort-Object FullName)) {
        $null = Assert-SafeRoot $item.FullName
        $files += @{ path = $item.FullName.Substring($root.Length + 1).Replace('\', '/'); sha256 = Get-Sha256 $item.FullName }
    }
    Write-NewText $Receipt (@{ schema = 'mra-demo-archive/v1'; kind = $Kind; version = $Version; directory = $root; files = $files } | ConvertTo-Json -Depth 6)
}

function Assert-Inventory([string]$Directory, [string]$Receipt, [string]$ExpectedKind, [string]$ExpectedVersion) {
    $root = Assert-SafeRoot $Directory
    $null = Assert-SafeRoot $Receipt
    if (-not (Test-Path -LiteralPath $Receipt -PathType Leaf)) {
        throw "Missing ownership receipt; partial or unrelated installation refused: $Directory"
    }
    $record = Get-Content -LiteralPath $Receipt -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($record.schema -cne 'mra-demo-archive/v1' -or $record.kind -cne $ExpectedKind -or
        $record.version -cne $ExpectedVersion -or $record.directory -ine $root -or @($record.files).Count -eq 0) {
        throw 'The installation receipt does not match this runtime or source snapshot.'
    }
    $known = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($file in $record.files) {
        if ($file.path -match '(^|/)\.\.?(/|$)' -or $file.path.Contains('\') -or $file.path.Contains(':') -or $file.path.StartsWith('/')) {
            throw 'Unsafe inventory entry.'
        }
        if (-not $known.Add($file.path)) { throw 'Duplicate inventory entry.' }
        Assert-FileHash (Join-Path $root $file.path) $file.sha256
    }
    foreach ($item in (Get-ChildItem -LiteralPath $root -Recurse -Force)) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Installation links are refused.' }
        if ($item.PSIsContainer) { continue }
        $relative = $item.FullName.Substring($root.Length + 1).Replace('\', '/')
        if ($item.FullName -ieq $Receipt -or $known.Contains($relative)) { continue }
        # Editable installation produces metadata and an owned local temporary directory.
        if ($ExpectedKind -eq 'source' -and ($relative.StartsWith('.local/') -or
            $relative.StartsWith('src/model_release_assurance.egg-info/'))) { continue }
        throw "Unexpected file in verified installation: $relative"
    }
}

function Invoke-Python([string]$Python, [string[]]$Arguments) {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python operation failed (exit $LASTEXITCODE). Existing files and evidence were retained." }
}

function Get-DefaultHome {
    $user = [Environment]::UserName -replace '[^A-Za-z0-9_.-]', '_'
    $dDrive = New-Object IO.DriveInfo -ArgumentList 'D:\'
    if ($dDrive.DriveType -ne [IO.DriveType]::Network -and (Test-Path -LiteralPath 'D:\' -PathType Container)) {
        $candidate = Assert-SafeRoot (Join-Path 'D:\MRA-Demo' $user)
        try { $null = [IO.Directory]::CreateDirectory($candidate); return $candidate }
        catch [UnauthorizedAccessException] { Write-Host 'D: is not writable; using local application data.' }
        catch [IO.IOException] { Write-Host 'D: is unavailable; using local application data.' }
    }
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'Set MRA_DEMO_HOME to an absolute local folder.' }
    return (Assert-SafeRoot (Join-Path (Join-Path $env:LOCALAPPDATA 'MRA-Demo') $user))
}

function Start-DemoInstaller {
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64' -or
        $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { throw 'This installer requires 64-bit x86 Windows.' }
    $installRoot = if ([string]::IsNullOrWhiteSpace($env:MRA_DEMO_HOME)) { Get-DefaultHome } else { Assert-SafeRoot $env:MRA_DEMO_HOME }
    $homeReceipt = Join-Path $installRoot 'mra-demo-home.json'
    if (Test-Path -LiteralPath $homeReceipt) {
        $null = Assert-SafeRoot $homeReceipt
        $record = Get-Content -LiteralPath $homeReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($record.schema -cne 'mra-demo-home/v1' -or $record.directory -ine $installRoot) { throw 'Unrelated installation home refused.' }
    } else {
        if ((Test-Path -LiteralPath $installRoot) -and @(Get-ChildItem -LiteralPath $installRoot -Force).Count -ne 0) {
            throw 'MRA_DEMO_HOME must be new, empty or previously created by this installer.'
        }
        $null = [IO.Directory]::CreateDirectory($installRoot)
        Write-NewText $homeReceipt (@{ schema = 'mra-demo-home/v1'; directory = $installRoot } | ConvertTo-Json)
    }
    [int]$port = 8765
    if (-not [string]::IsNullOrWhiteSpace($env:MRA_DEMO_PORT)) {
        if (-not [int]::TryParse($env:MRA_DEMO_PORT, [ref]$port) -or $port -lt 1024 -or $port -gt 65535) { throw 'MRA_DEMO_PORT must be 1024 through 65535.' }
    }
    if ($env:MRA_DEMO_RESEARCH_DATA_ROOT) { $null = Assert-SafeRoot $env:MRA_DEMO_RESEARCH_DATA_ROOT }
    Write-Host "Model Release Assurance Demo - installation and evidence: $installRoot"
    $downloads = Join-Path $installRoot 'downloads'
    $runtime = Join-Path $installRoot ("runtime\python-" + $PythonVersion)
    $release = Join-Path $installRoot ("demo-" + $DemoRevision.Substring(0, 7))
    $source = Join-Path $release 'source'
    $venv = Join-Path $release 'environment'
    $data = Join-Path $release 'console-data'
    $datasets = Join-Path $release 'public-datasets'
    foreach ($ownedPath in @($downloads, $runtime, $release, $source, $venv, $data, $datasets)) { $null = Assert-SafeRoot $ownedPath }
    $null = [IO.Directory]::CreateDirectory($downloads)
    $null = [IO.Directory]::CreateDirectory($release)
    $pythonArchive = Join-Path $downloads ("python." + $PythonVersion + '.nupkg')
    $sourceArchive = Join-Path $downloads ("demo-" + $DemoRevision + '.zip')
    Get-Download ("https://api.nuget.org/v3-flatcontainer/python/" + $PythonVersion + "/python." + $PythonVersion + '.nupkg') $pythonArchive $PythonHash
    Get-Download ("https://codeload.github.com/elmontu/AI_ModeL_Check/zip/" + $DemoRevision) $sourceArchive $SourceHash
    $runtimeReceipt = Join-Path $runtime 'mra-archive.json'
    if (-not (Test-Path -LiteralPath $runtime)) {
        Expand-VerifiedArchive $pythonArchive $runtime ''
        Save-Inventory $runtime $runtimeReceipt 'python' $PythonVersion
    }
    Assert-Inventory $runtime $runtimeReceipt 'python' $PythonVersion
    $python = Join-Path $runtime 'tools\python.exe'
    $signature = Get-AuthenticodeSignature -LiteralPath $python
    if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch '(^|, )O=Python Software Foundation(,|$)') {
        throw 'The official Python executable signature could not be verified.'
    }
    $sourceReceipt = Join-Path $source 'mra-archive.json'
    if (-not (Test-Path -LiteralPath $source)) {
        Expand-VerifiedArchive $sourceArchive $source ("AI_ModeL_Check-" + $DemoRevision + '/')
        Save-Inventory $source $sourceReceipt 'source' $DemoRevision
    }
    Assert-Inventory $source $sourceReceipt 'source' $DemoRevision
    $constraint = Join-Path $release 'validated-requirements.txt'
    $null = Assert-SafeRoot $constraint
    $constraintText = "scikit-learn==1.6.1" + [Environment]::NewLine
    if (-not (Test-Path -LiteralPath $constraint)) { Write-NewText $constraint $constraintText }
    if ([IO.File]::ReadAllText($constraint) -cne $constraintText) { throw 'Installer requirements constraint changed.' }
    $probe = Join-Path $release ('prepare_demo_data-' + $DataProbeHash.Substring(0, 12) + '.py')
    $null = Assert-SafeRoot $probe
    if (-not (Test-Path -LiteralPath $probe)) {
        $bytes = [Convert]::FromBase64String($DataProbeBase64)
        $stream = [IO.File]::Open($probe, [IO.FileMode]::CreateNew)
        try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
    }
    Assert-FileHash $probe $DataProbeHash
    # Keep installation writes, pip caches and Python paths inside this owned home.
    foreach ($name in @('PYTHONHOME', 'PYTHONPATH', 'PIP_TARGET', 'PIP_PREFIX', 'PIP_USER')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    $env:PIP_CONFIG_FILE = 'NUL'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $env:PIP_NO_CACHE_DIR = '1'
    $env:PIP_CONSTRAINT = $constraint
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PYTHONUNBUFFERED = '1'
    $env:PYTHONSAFEPATH = '1'
    $temporary = Join-Path $installRoot 'temporary'
    $null = Assert-SafeRoot $temporary
    $null = [IO.Directory]::CreateDirectory($temporary)
    $env:TEMP = $temporary
    $env:TMP = $temporary
    Write-Host 'Installing or validating the web service, worker and scientific environment...'
    $launcher = Join-Path $source 'scripts\start_demo.py'
    Invoke-Python $python @('-I', '-B', $launcher, '--venv', $venv, '--data', $data, '--install-only')
    $environmentPython = Join-Path $venv 'Scripts\python.exe'
    Write-Host 'Checking all four downloaded public datasets...'
    Invoke-Python $environmentPython @('-I', '-B', $probe, '--output', $datasets)
    Assert-Inventory $source $sourceReceipt 'source' $DemoRevision
    if ($env:MRA_DEMO_SETUP_ONLY -eq '1') {
        Write-Host "Setup complete. Public datasets: $datasets"
        return
    }
    # Refuse an occupied port before scheduling a browser opener.
    $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $port)
    try { $listener.Start() } finally { $listener.Stop() }
    $url = "http://127.0.0.1:$port/"
    Write-Host "Starting the demo at $url"
    Write-Host 'Keep this window open. Press Ctrl+C to stop the web service and worker.'
    $opener = $null
    try {
        if ($env:MRA_DEMO_NO_BROWSER -ne '1') {
            $opener = Start-Job -ArgumentList $url -ScriptBlock {
                param($url)
                for ($attempt = 0; $attempt -lt 90; $attempt++) {
                    try {
                        $status = Invoke-RestMethod -Uri ($url + 'api/status') -TimeoutSec 2
                        if ($status.worker_online) { Start-Process $url; return }
                    } catch {}
                    Start-Sleep -Seconds 1
                }
            }
        }
        $arguments = @('-I', '-B', $launcher, '--venv', $venv, '--data', $data, '--port', [string]$port)
        if ($env:MRA_DEMO_RESEARCH_DATA_ROOT) { $arguments += @('--research-data-root', $env:MRA_DEMO_RESEARCH_DATA_ROOT) }
        Invoke-Python $python $arguments
    } finally {
        if ($null -ne $opener) { Stop-Job $opener; Remove-Job $opener }
    }
}

# MRA RUN INSTALLER
try { Start-DemoInstaller; exit 0 }
catch {
    Write-Host ''
    Write-Host ('Setup stopped: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'No existing model evidence was removed. Keep this window for diagnostics.'
    exit 1
}
