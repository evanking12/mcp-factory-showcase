# Troubleshooting

Having issues with `setup-dev.ps1` or `run_fixtures.ps1`? Check here.

## Common Issues

### ❌ "dumpbin.exe not found" or "Could not locate Visual Studio developer environment"

**Problem:** The script can't find `dumpbin.exe`, which is part of Visual Studio Build Tools.

**Solution:**

1. **Install Visual Studio Build Tools** (or Visual Studio 2022 Community/Enterprise)
   - Download: https://visualstudio.microsoft.com/downloads/
   - Choose "Visual Studio Build Tools 2022" (or Community Edition)
   
2. **During installation, select the C++ workload:**
   - Check "Desktop development with C++"
   - This installs dumpbin.exe and required development tools
   
3. **After installation, re-run the setup:**
   ```powershell
   .\scripts\setup-dev.ps1
   ```

**Still not found?** Manually specify dumpbin location:
```powershell
.\scripts\run_fixtures.ps1 -DumpbinExe "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.39.33519\bin\Hostx64\x64\dumpbin.exe"
```

---

### ❌ "python: command not found" or "Python 3.8+ not detected"

**Problem:** Python isn't installed or not in your PATH.

**Solution:**

1. **Check if Python is installed:**
   ```powershell
   python --version
   # or try
   python3 --version
   ```

2. **If not installed:**
   - Download from https://www.python.org/downloads/
   - Choose Python 3.8 or later
   - **Important:** Check "Add Python to PATH" during installation

3. **After installation, restart PowerShell and try again:**
   ```powershell
   .\scripts\setup-dev.ps1
   ```

---

### ❌ "git: command not found"

**Problem:** Git isn't installed or not in your PATH.

**Solution:**

1. **Install Git for Windows:**
   - Download: https://git-scm.com/download/win
   - Run the installer and accept defaults

2. **Restart PowerShell** and clone the repo:
   ```powershell
   git clone "REPOSITORY_URL"
   cd mcp-factory
   .\scripts\setup-dev.ps1
   ```

---

### ❌ "Set-ExecutionPolicy: Access Denied"

**Problem:** PowerShell execution policy is blocking script execution.

**Solution:**

Set execution policy for the current session only (doesn't affect system):
```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-dev.ps1
```

---

### ❌ "vcpkg.exe not found" or "vcpkg bootstrap failed"

**Problem:** vcpkg download or extraction failed.

**Solution:**

1. **Check if vcpkg directory exists:**
   ```powershell
   Test-Path "$env:USERPROFILE\Downloads\vcpkg"
   ```

2. **If it exists but is corrupted, delete and retry:**
   ```powershell
   Remove-Item "$env:USERPROFILE\Downloads\vcpkg" -Recurse -Force
   .\scripts\setup-dev.ps1
   ```

3. **If download is slow, manually download vcpkg:**
   - https://github.com/Microsoft/vcpkg/releases
   - Extract to `$env:USERPROFILE\Downloads\vcpkg`
   - Re-run setup

---

### ❌ "zstd not found" or "sqlite3 not found" (during fixture run)

**Problem:** vcpkg failed to build the test libraries.

**Solution:**

1. **Check vcpkg installation:**
   ```powershell
   & "$env:USERPROFILE\Downloads\vcpkg\vcpkg.exe" list
   ```

2. **If empty, rebuild:**
   ```powershell
   .\scripts\run_fixtures.ps1 -BootstrapVcpkg
   ```

3. **If it hangs on zstd/sqlite3 build:**
   - This can take 10+ minutes on slower machines
   - Check Task Manager for vcpkg.exe CPU usage (should be active)
   - Don't interrupt—let it complete

---

### ❌ Permission Denied or "Access to the path is denied"

**Problem:** File permissions or antivirus blocking access.

**Solution:**

1. **Disable antivirus temporarily** (Windows Defender, Norton, McAfee, etc.)
2. **Run as Administrator:**
   - Right-click PowerShell → "Run as Administrator"
   - Then run `.\scripts\setup-dev.ps1`
3. **Try a different output directory:**
   ```powershell
   .\scripts\run_fixtures.ps1 -OutDir "C:\temp\mcp_output"
   ```

---

## Still Not Working?

1. **Check the full error message** — Copy the last 5-10 lines of output
2. **Verify prerequisites:**
   ```powershell
   python --version           # Should be 3.8+
   git --version              # Should be installed
   dumpbin /?                 # Should show help
   ```

3. **Reach out:**
   - Open a GitHub issue: the Issues tab of this repository
   - Include your OS version, error output, and `python --version` output
   - Tag @evanking12 for faster response

---

## Getting Help

- **Docs:** [docs/architecture.md](architecture.md)
- **Issues:** the Issues tab of this repository
- **Contact:** @evanking12 on GitHub
