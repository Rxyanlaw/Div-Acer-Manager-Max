<p align="center">
  <img src="https://github.com/user-attachments/assets/6d383e82-8221-438b-9d6d-a19e998fcc59" alt="icon" width="80" style="vertical-align: middle;">
</p>

<h1 align="center">
  Div Acer Manager Max
</h1>

**Div Acer Manager Max** is a feature-rich **Windows** GUI utility for Acer laptops. It provides fan control, performance modes, battery optimization, backlight settings, and more — all wrapped in a modern Avalonia-based UI.

> [!NOTE]
> This is the Windows version of the project. For Linux users, please use the original Linuwu-Sense based version from an earlier release.

> [!CAUTION]
> Project is under passive development.

![Title Image](https://github.com/user-attachments/assets/a60898a6-a2b8-432e-b5a2-8d0a45c63484)


<h4 align="center">
⭐ Please star this repository to show support. It motivates me to make the project better for everyone
</h4>  

## ✨ Features

### ✅ Fully Implemented

* 🔋 **Performance / Thermal Profiles**
  Control Windows power schemes: Power Saver, Balanced, High Performance
  Automatically adjusted based on AC/battery status

* 🌡 **System Monitoring Dashboard**
  Real-time CPU/GPU temperature and usage monitoring via WMI
  Fan speed display (requires Open Hardware Monitor for detailed readings)

* 💻 **Live System Info Display**
  Shows real-time performance profile, system information, and more

* 🧠 **Smart Daemon (Low Resource Use)**

  * Auto-detects feature support per device
  * Communicates with GUI in real-time via Named Pipes
  * Lightweight design
  * Can run **independently** of GUI

* 🖥️ **Modern GUI**

  * Avalonia-based, clean and responsive
  * Realtime Monitoring with Dashboard
  * Dynamic UI hides unsupported features
  * Real-time feedback from daemon

### ⚠️ Windows Limitations

Some features require Acer's official software (NitroSense/PredatorSense) on Windows:

* Fan speed control
* Battery calibration and limiter
* Keyboard RGB control
* Boot animation/sound settings
* LCD override

These features are exposed in the UI for future compatibility when Acer provides WMI interfaces.

## 🧭 Compatibility

**Supported Operating Systems:**
- Windows 10 (64-bit)
- Windows 11 (64-bit)

**Supported Laptops:**
- Acer Predator series
- Acer Nitro series
- Other Acer gaming laptops

Check your device compatibility here: [Compatibility List](https://github.com/PXDiv/Div-Acer-Manager-Max/blob/main/Compatibility.md)


## 🖥️ DAMX Installation Guide (Windows)

### 📦 Automated Installation

1. Download the latest release from the **Releases** section.

2. Extract the downloaded package.

3. Right-click \`Install-DAMX.ps1\` and select **"Run with PowerShell"** (as Administrator)

4. Follow the on-screen prompts.

5. Done! You can now launch DAMX from the desktop shortcut or Start Menu.


### 🔧 Manual Installation

1. Download the latest release from the **Releases** section.

2. Extract the package to \`C:\Program Files\DAMX\`

3. Create a shortcut to \`DivAcerManagerMax.exe\` on your desktop

4. (Optional) Run the daemon as a Windows service for background functionality


## 📋 Requirements

* .NET 9.0 Runtime (Windows)
* Administrator privileges for full functionality
* Optional: Open Hardware Monitor for detailed sensor readings


## 🖥️ Troubleshooting

You can check the logs at \`C:\ProgramData\DAMX\DAMX_Daemon_Log.log\`

If you get UNKNOWN as Laptop type, the application couldn't detect your Acer laptop model via WMI.

Also, check out the [FAQ page](https://github.com/PXDiv/Div-Acer-Manager-Max/blob/main/FAQ.md) before opening any issues.

Please open a new issue or discussion and include the logs to get support and help the project grow.

## Screenshots 
![image](https://github.com/user-attachments/assets/10d44e8c-14e4-4441-b60c-538af1840cf6)
![image](https://github.com/user-attachments/assets/89217b26-b94c-4c78-8fe8-3de2b22a7095)
![image](https://github.com/user-attachments/assets/72a7b944-5efc-4520-83b6-88069fc05723)
![image](https://github.com/user-attachments/assets/f9a9d663-70c6-482e-a0c4-15a4ea08a8d2)


## 🤝 Contributing

* Report bugs or request features via GitHub Issues
* Submit pull requests to improve code or UI
* Help test on different Acer laptop models



## 📄 License

This project is licensed under the **GNU General Public License v3.0**.  
See the [LICENSE](LICENSE) file for details.
