# DAMX Windows Installer Script
# Requires Administrator privileges
# Usage: Right-click -> Run with PowerShell (as Administrator)

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

# Constants
$ScriptVersion = "1.0.0"
$GitHubRepo = "PXDiv/Div-Acer-Manager-Max"
$InstallDir = "$env:ProgramFiles\DAMX"
$DataDir = "$env:ProgramData\DAMX"
$ServiceName = "DAMXDaemon"
$DesktopShortcut = "$env:Public\Desktop\DAMX.lnk"
$StartMenuPath = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\DAMX.lnk"

# Colors
function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Show-Banner {
    Clear-Host
    Write-ColorOutput "==========================================" "Cyan"
    Write-ColorOutput "    DAMX Windows Installer v$ScriptVersion    " "Cyan"
    Write-ColorOutput "    Acer Laptop Manager for Windows     " "Cyan"
    Write-ColorOutput "==========================================" "Cyan"
    Write-Host ""
}

function Get-LatestRelease {
    Write-ColorOutput "Fetching latest release information..." "Yellow"
    
    $apiUrl = "https://api.github.com/repos/$GitHubRepo/releases/latest"
    
    try {
        $releaseInfo = Invoke-RestMethod -Uri $apiUrl -Method Get
        
        $script:ReleaseTag = $releaseInfo.tag_name
        $script:ReleaseName = $releaseInfo.name
        
        # Find Windows package asset
        $windowsAsset = $releaseInfo.assets | Where-Object { $_.name -like "*windows*.zip" -or $_.name -like "*win*.zip" }
        
        if ($windowsAsset) {
            $script:DownloadUrl = $windowsAsset.browser_download_url
        } else {
            # Fallback to first zip file
            $zipAsset = $releaseInfo.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
            if ($zipAsset) {
                $script:DownloadUrl = $zipAsset.browser_download_url
            } else {
                Write-ColorOutput "Error: No suitable Windows package found in the latest release" "Red"
                return $false
            }
        }
        
        Write-ColorOutput "Latest release found: $ReleaseName" "Green"
        return $true
    }
    catch {
        Write-ColorOutput "Error: Failed to fetch release information: $_" "Red"
        return $false
    }
}

function Install-DAMX {
    Write-ColorOutput "Starting DAMX installation..." "Cyan"
    
    # Create temp directory
    $tempDir = Join-Path $env:TEMP "damx-install-$(Get-Date -Format 'yyyyMMddHHmmss')"
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    
    try {
        # Download package
        Write-ColorOutput "Downloading DAMX package..." "Yellow"
        $packagePath = Join-Path $tempDir "damx.zip"
        
        if ($DownloadUrl) {
            Invoke-WebRequest -Uri $DownloadUrl -OutFile $packagePath
        } else {
            Write-ColorOutput "No download URL available. Manual installation required." "Yellow"
            return $false
        }
        
        # Extract package
        Write-ColorOutput "Extracting package..." "Yellow"
        Expand-Archive -Path $packagePath -DestinationPath $tempDir -Force
        
        # Create installation directories
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
        New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
        
        # Stop existing service if running
        $existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($existingService) {
            Write-ColorOutput "Stopping existing DAMX service..." "Yellow"
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        }
        
        # Copy files
        Write-ColorOutput "Installing files..." "Yellow"
        
        # Find extracted content
        $extractedDirs = Get-ChildItem -Path $tempDir -Directory
        $sourceDir = if ($extractedDirs.Count -eq 1) { $extractedDirs[0].FullName } else { $tempDir }
        
        # Copy GUI files
        if (Test-Path "$sourceDir\DAMX-GUI") {
            Copy-Item -Path "$sourceDir\DAMX-GUI\*" -Destination $InstallDir -Recurse -Force
        } elseif (Test-Path "$sourceDir\DivAcerManagerMax") {
            Copy-Item -Path "$sourceDir\DivAcerManagerMax\*" -Destination $InstallDir -Recurse -Force
        }
        
        # Copy Daemon files
        if (Test-Path "$sourceDir\DAMX-Daemon") {
            $daemonDir = Join-Path $InstallDir "daemon"
            New-Item -ItemType Directory -Path $daemonDir -Force | Out-Null
            Copy-Item -Path "$sourceDir\DAMX-Daemon\*" -Destination $daemonDir -Recurse -Force
        } elseif (Test-Path "$sourceDir\DAMM-Daemon") {
            $daemonDir = Join-Path $InstallDir "daemon"
            New-Item -ItemType Directory -Path $daemonDir -Force | Out-Null
            Copy-Item -Path "$sourceDir\DAMM-Daemon\*" -Destination $daemonDir -Recurse -Force
        }
        
        # Create shortcuts
        Write-ColorOutput "Creating shortcuts..." "Yellow"
        
        $guiExe = Get-ChildItem -Path $InstallDir -Filter "*.exe" | Select-Object -First 1
        if ($guiExe) {
            # Desktop shortcut
            $WshShell = New-Object -ComObject WScript.Shell
            $Shortcut = $WshShell.CreateShortcut($DesktopShortcut)
            $Shortcut.TargetPath = $guiExe.FullName
            $Shortcut.WorkingDirectory = $InstallDir
            $Shortcut.Description = "Div Acer Manager Max"
            $Shortcut.Save()
            
            # Start Menu shortcut
            $Shortcut = $WshShell.CreateShortcut($StartMenuPath)
            $Shortcut.TargetPath = $guiExe.FullName
            $Shortcut.WorkingDirectory = $InstallDir
            $Shortcut.Description = "Div Acer Manager Max"
            $Shortcut.Save()
        }
        
        Write-ColorOutput "DAMX installed successfully!" "Green"
        Write-ColorOutput "" "White"
        Write-ColorOutput "Installation complete!" "Cyan"
        Write-ColorOutput "You can now run DAMX from the desktop shortcut or Start Menu." "White"
        
        return $true
    }
    catch {
        Write-ColorOutput "Error during installation: $_" "Red"
        return $false
    }
    finally {
        # Cleanup temp directory
        if (Test-Path $tempDir) {
            Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Uninstall-DAMX {
    Write-ColorOutput "Uninstalling DAMX..." "Yellow"
    
    try {
        # Stop and remove service
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service) {
            Write-ColorOutput "Stopping DAMX service..." "Yellow"
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            
            # Remove service
            sc.exe delete $ServiceName | Out-Null
        }
        
        # Remove shortcuts
        if (Test-Path $DesktopShortcut) {
            Remove-Item -Path $DesktopShortcut -Force
        }
        if (Test-Path $StartMenuPath) {
            Remove-Item -Path $StartMenuPath -Force
        }
        
        # Remove installation directory
        if (Test-Path $InstallDir) {
            Remove-Item -Path $InstallDir -Recurse -Force
        }
        
        # Optionally remove data directory (ask user)
        if (Test-Path $DataDir) {
            $response = Read-Host "Remove configuration and log files? (y/N)"
            if ($response -eq 'y' -or $response -eq 'Y') {
                Remove-Item -Path $DataDir -Recurse -Force
            }
        }
        
        Write-ColorOutput "DAMX uninstalled successfully!" "Green"
        return $true
    }
    catch {
        Write-ColorOutput "Error during uninstallation: $_" "Red"
        return $false
    }
}

# Main execution
Show-Banner

if (-not (Test-Administrator)) {
    Write-ColorOutput "This script requires Administrator privileges." "Red"
    Write-ColorOutput "Please right-click and select 'Run as Administrator'." "Yellow"
    pause
    exit 1
}

if ($Uninstall) {
    Uninstall-DAMX
} else {
    # Check for Acer laptop
    $computerSystem = Get-CimInstance Win32_ComputerSystem
    $manufacturer = $computerSystem.Manufacturer
    
    if ($manufacturer -notlike "*Acer*") {
        Write-ColorOutput "Warning: This does not appear to be an Acer laptop." "Yellow"
        Write-ColorOutput "Manufacturer detected: $manufacturer" "White"
        $response = Read-Host "Continue anyway? (y/N)"
        if ($response -ne 'y' -and $response -ne 'Y') {
            exit 0
        }
    }
    
    # Fetch latest release
    if (Get-LatestRelease) {
        Install-DAMX
    } else {
        Write-ColorOutput "Could not fetch release information." "Red"
        Write-ColorOutput "Please download manually from:" "Yellow"
        Write-ColorOutput "https://github.com/$GitHubRepo/releases" "Cyan"
    }
}

Write-Host ""
pause
