$ErrorActionPreference = 'Stop'
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$SecretDirectory = Join-Path $env:LOCALAPPDATA 'RichardDailyDone'
$SecretPath = Join-Path $SecretDirectory 'deepseek.key.dpapi'
New-Item -ItemType Directory -Path $SecretDirectory -Force | Out-Null
$Secret = Read-Host 'Enter the DeepSeek API Key (input is hidden)' -AsSecureString
$Encrypted = ConvertFrom-SecureString -SecureString $Secret
[IO.File]::WriteAllText($SecretPath, $Encrypted, $Utf8NoBom)
$Acl = Get-Acl -LiteralPath $SecretPath
$Acl.SetAccessRuleProtection($true, $false)
$Rule = New-Object System.Security.AccessControl.FileSystemAccessRule([Security.Principal.WindowsIdentity]::GetCurrent().Name, 'FullControl', 'Allow')
$Acl.AddAccessRule($Rule)
Set-Acl -LiteralPath $SecretPath -AclObject $Acl
Write-Output ('Encrypted secret saved for the current Windows account at ' + $SecretPath)
Write-Output 'Set DEEPSEEK_SECRET_FILE to this path for the self-hosted runner account.'

