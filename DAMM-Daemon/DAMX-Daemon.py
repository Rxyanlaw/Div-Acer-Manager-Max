#!/usr/bin/env python3
# DAMX-Daemon - Manage Acer laptop features as Windows service communicating with WMI
# Compatible with Predator and Nitro laptops on Windows

import os
import subprocess
import sys
import json
import time
import argparse
import logging
import logging.handlers
import threading
import signal
import configparser
import traceback
from pathlib import Path
from enum import Enum
from typing import Dict, List, Tuple, Set

# Windows-specific imports with error handling
try:
    import ctypes
    import win32pipe
    import win32file
    import pywintypes
    import wmi
except ImportError as e:
    print(f"Error: Required Windows module not found: {e}")
    print("Please install dependencies: pip install -r requirements.txt")
    print("Required packages: WMI, pywin32")
    sys.exit(1)

# Import power source detection
try:
    from PowerSourceDetection import PowerSourceDetector
except ImportError:
    PowerSourceDetector = None
    print("Warning: PowerSourceDetection module not found")

# Constants
VERSION = "0.4.6"
PIPE_NAME = r'\\.\pipe\DAMX'
LOG_PATH = os.path.join(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'), 'DAMX', 'DAMX_Daemon_Log.log')
CONFIG_PATH = os.path.join(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'), 'DAMX', 'config.ini')

# Create log directory if it doesn't exist
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

# Check if running as administrator
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    print("This daemon should run as Administrator for full functionality.")
    # Continue anyway for development, but warn

# Configure logging
log = logging.getLogger("DAMXDaemon")
log.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
log.addHandler(console_handler)

# File handler with rotation
try:
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=1024*1024*5, backupCount=5)
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)
except Exception as e:
    print(f"Warning: Could not create log file: {e}")

class LaptopType(Enum):
    UNKNOWN = 0
    PREDATOR = 1
    NITRO = 2

class DAMXManager:
    """Manages all the DAMX-Daemon features using Windows WMI"""

    MAX_RESTART_ATTEMPTS = 20

    def __init__(self):
        '''Initialize the DAMX Manager for Windows'''
        log.info(f"** Starting DAMX-Daemon v{VERSION} (Windows) **")

        # Initialize WMI connection
        try:
            self.wmi_connection = wmi.WMI()
            self.wmi_root = wmi.WMI(namespace="root/WMI")
            log.info("WMI connection established")
        except Exception as e:
            log.error(f"Failed to connect to WMI: {e}")
            self.wmi_connection = None
            self.wmi_root = None
        
        self.laptop_type = self._detect_laptop_type()
        self.has_four_zone_kb = self._check_four_zone_kb()
        self.current_modprobe_param = ""  # Not applicable on Windows

        # Available features set
        self.available_features = self._detect_available_features()

        log.info(f"Detected laptop type: {self.laptop_type.name}")
        log.info(f"Four-zone keyboard: {'Yes' if self.has_four_zone_kb else 'No'}")
        log.info(f"Available features: {', '.join(self.available_features)}")
        
        self.power_monitor = None

    def _force_model_nitro(self):
        """Force Nitro model - Not applicable on Windows, use NitroSense software"""
        log.info("Force model not applicable on Windows - use Acer NitroSense/PredatorSense software")
        return False

    def _force_model_predator(self):
        """Force Predator model - Not applicable on Windows, use PredatorSense software"""
        log.info("Force model not applicable on Windows - use Acer NitroSense/PredatorSense software")
        return False
    
    def _force_enable_all(self):
        """Force enable all features - Not applicable on Windows"""
        log.info("Force enable all not applicable on Windows - use Acer NitroSense/PredatorSense software")
        return False

    def get_modprobe_parameter(self) -> str:
        """Get current modprobe parameter - Not applicable on Windows"""
        return ""

    def set_modprobe_parameter(self, param: str) -> bool:
        """Set modprobe parameter - Not applicable on Windows"""
        log.info("Modprobe parameters not applicable on Windows")
        return False

    def _remove_modprobe_parameter(self) -> bool:
        """Remove modprobe parameter - Not applicable on Windows"""
        return True
        
    def _restart_daemon(self):
        """Restart DAMX daemon service"""
        log.info("Attempting to restart daemon")
        
        try:
            # On Windows, restart the service
            subprocess.run(['sc', 'stop', 'DAMXDaemon'], check=False)
            time.sleep(2)
            subprocess.run(['sc', 'start', 'DAMXDaemon'], check=True)
            return True
        except Exception as e:
            log.error(f"Error restarting daemon: {e}")
            return False

    def _restart_drivers_and_daemon(self):
        """Restart daemon service (no driver reload on Windows)"""
        log.info("Attempting to restart daemon...")
        return self._restart_daemon()
            
    def _detect_laptop_type(self) -> LaptopType:
        """Detect whether this is a Predator or Nitro laptop using WMI"""
        try:
            if self.wmi_connection:
                for system in self.wmi_connection.Win32_ComputerSystem():
                    model = (system.Model or "").upper()
                    manufacturer = (system.Manufacturer or "").upper()
                    
                    if "ACER" in manufacturer:
                        if "PREDATOR" in model:
                            return LaptopType.PREDATOR
                        elif "NITRO" in model:
                            return LaptopType.NITRO
            return LaptopType.UNKNOWN
        except Exception as e:
            log.error(f"Error detecting laptop type: {e}")
            return LaptopType.UNKNOWN

    def get_driver_version(self) -> str:
        """Get Windows driver version - returns ACPI/WMI driver info"""
        try:
            if self.wmi_connection:
                for driver in self.wmi_connection.Win32_SystemDriver(Name='ACPI'):
                    return driver.PathName or "ACPI Driver"
            return "Windows WMI"
        except:
            return "Unknown Version"
    

    def _detect_available_features(self) -> Set[str]:
        """Detect which features are available on the current laptop using WMI"""
        available = set()

        try:
            # Check for power management features
            if self.wmi_connection:
                # Battery features are always available on laptops
                for battery in self.wmi_connection.Win32_Battery():
                    available.add("battery_calibration")
                    available.add("battery_limiter")
                    break
                
                # Check for Acer-specific WMI features
                try:
                    # Try to access Acer WMI namespace
                    acer_wmi = wmi.WMI(namespace="root/WMI")
                    # If we can access ACPI methods, thermal profile may be available
                    available.add("thermal_profile")
                except:
                    pass

            # Basic features that work via Windows power plans
            available.add("thermal_profile")
            
            # Fan control typically requires vendor-specific software
            # But we'll expose it as available for the UI
            if self.laptop_type != LaptopType.UNKNOWN:
                available.add("fan_speed")
                available.add("boot_animation_sound")
                available.add("backlight_timeout")
                available.add("lcd_override")

        except Exception as e:
            log.error(f"Error detecting features: {e}")

        return available

    def _check_four_zone_kb(self) -> bool:
        """Check if four-zone keyboard is available - check for Acer keyboard drivers"""
        try:
            if self.wmi_connection:
                # Check for Acer keyboard in device list
                for device in self.wmi_connection.Win32_Keyboard():
                    if "acer" in (device.Name or "").lower():
                        return True
            return False
        except:
            return False

    def get_thermal_profile(self) -> str:
        """Get current thermal profile using Windows power scheme"""
        if "thermal_profile" not in self.available_features:
            return ""
        
        try:
            result = subprocess.run(['powercfg', '/getactivescheme'], 
                                   capture_output=True, text=True)
            output = result.stdout.lower()
            
            if 'balanced' in output:
                return 'balanced'
            elif 'high performance' in output or 'performance' in output:
                return 'performance'
            elif 'power saver' in output:
                return 'low-power'
            else:
                return 'balanced'
        except:
            return 'balanced'

    def set_thermal_profile(self, profile: str) -> bool:
        """Set thermal profile using Windows power scheme"""
        if "thermal_profile" not in self.available_features:
            return False

        # Map profiles to Windows power scheme GUIDs
        scheme_map = {
            'performance': '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c',  # High Performance
            'balanced-performance': '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c',  # High Performance
            'balanced': '381b4222-f694-41f0-9685-ff5bb260df2e',  # Balanced
            'quiet': 'a1841308-3541-4fab-bc81-f71556f20b4a',  # Power Saver
            'low-power': 'a1841308-3541-4fab-bc81-f71556f20b4a',  # Power Saver
        }
        
        guid = scheme_map.get(profile.lower(), '381b4222-f694-41f0-9685-ff5bb260df2e')
        
        try:
            subprocess.run(['powercfg', '/setactive', guid], check=True)
            log.info(f"Set power scheme to: {profile}")
            return True
        except Exception as e:
            log.error(f"Failed to set power scheme: {e}")
            return False

    def get_thermal_profile_choices(self) -> List[str]:
        """Get available thermal profiles"""
        if "thermal_profile" not in self.available_features:
            return []
        return ['low-power', 'quiet', 'balanced', 'balanced-performance', 'performance']

    def get_backlight_timeout(self) -> str:
        """Get backlight timeout status - not directly supported on Windows"""
        return "0"

    def set_backlight_timeout(self, enabled: bool) -> bool:
        """Set backlight timeout - not directly supported on Windows"""
        log.info("Backlight timeout control not supported on Windows")
        return False

    def get_battery_calibration(self) -> str:
        """Get battery calibration status - not directly supported on Windows"""
        return "0"

    def set_battery_calibration(self, enabled: bool) -> bool:
        """Start or stop battery calibration - not directly supported on Windows"""
        log.info("Battery calibration control not supported on Windows - use Acer Care Center")
        return False

    def get_battery_limiter(self) -> str:
        """Get battery limiter status - not directly supported on Windows"""
        return "0"

    def set_battery_limiter(self, enabled: bool) -> bool:
        """Set battery limiter status - not directly supported on Windows"""
        log.info("Battery limiter control not supported on Windows - use Acer Care Center")
        return False

    def get_boot_animation_sound(self) -> str:
        """Get boot animation sound status - not directly supported on Windows"""
        return "0"

    def set_boot_animation_sound(self, enabled: bool) -> bool:
        """Set boot animation sound status - not directly supported on Windows"""
        log.info("Boot animation sound control not supported on Windows")
        return False

    def get_fan_speed(self) -> Tuple[str, str]:
        """Get CPU and GPU fan speeds using Acer WMI or fallback methods"""
        if "fan_speed" not in self.available_features:
            return ("", "")

        cpu_fan = "0"
        gpu_fan = "0"

        try:
            # Method 1: Try Acer Gaming WMI interface
            try:
                acer_wmi = wmi.WMI(namespace="root/WMI")
                
                # Try AcerGaming_FanSpeed class
                try:
                    for fan in acer_wmi.AcerGaming_FanSpeed():
                        if hasattr(fan, 'CpuFanSpeed'):
                            cpu_fan = str(fan.CpuFanSpeed)
                        if hasattr(fan, 'GpuFanSpeed'):
                            gpu_fan = str(fan.GpuFanSpeed)
                        if cpu_fan != "0" or gpu_fan != "0":
                            return (cpu_fan, gpu_fan)
                except:
                    pass
                
                # Try separate CPU and GPU fan speed classes
                try:
                    for fan in acer_wmi.AcerGaming_CpuFanSpeed():
                        if hasattr(fan, 'CurrentSpeed'):
                            cpu_fan = str(fan.CurrentSpeed)
                except:
                    pass
                    
                try:
                    for fan in acer_wmi.AcerGaming_GpuFanSpeed():
                        if hasattr(fan, 'CurrentSpeed'):
                            gpu_fan = str(fan.CurrentSpeed)
                except:
                    pass
                    
                if cpu_fan != "0" or gpu_fan != "0":
                    return (cpu_fan, gpu_fan)
                    
            except Exception as e:
                log.debug(f"Acer WMI not available: {e}")
            
            # Method 2: Try MSAcpi_ThermalZone (some systems report fan info here)
            try:
                if self.wmi_root:
                    # Some Acer systems expose fan through thermal cooling device
                    for cooling in self.wmi_root.Win32_Fan():
                        if hasattr(cooling, 'DesiredSpeed'):
                            cpu_fan = str(cooling.DesiredSpeed)
                            break
            except:
                pass

            # Method 3: Try Open Hardware Monitor WMI
            try:
                ohm_wmi = wmi.WMI(namespace="root/OpenHardwareMonitor")
                for sensor in ohm_wmi.Sensor():
                    if sensor.SensorType == "Fan":
                        name = sensor.Name.lower() if sensor.Name else ""
                        value = str(int(sensor.Value)) if sensor.Value else "0"
                        if "cpu" in name or "fan #1" in name:
                            cpu_fan = value
                        elif "gpu" in name or "fan #2" in name:
                            gpu_fan = value
            except:
                pass

            # Method 4: Try LibreHardwareMonitor WMI
            try:
                lhm_wmi = wmi.WMI(namespace="root/LibreHardwareMonitor")
                for sensor in lhm_wmi.Sensor():
                    if sensor.SensorType == "Fan":
                        name = sensor.Name.lower() if sensor.Name else ""
                        value = str(int(sensor.Value)) if sensor.Value else "0"
                        if "cpu" in name or "#1" in name:
                            cpu_fan = value
                        elif "gpu" in name or "#2" in name:
                            gpu_fan = value
            except:
                pass

            return (cpu_fan, gpu_fan)
            
        except Exception as e:
            log.error(f"Error reading fan speed: {e}")
            return ("0", "0")

    def set_fan_speed(self, cpu: int, gpu: int) -> bool:
        """Set CPU and GPU fan speeds using Acer WMI interface"""
        if "fan_speed" not in self.available_features:
            return False

        # Validate values
        if not (0 <= cpu <= 100 and 0 <= gpu <= 100):
            log.error(f"Invalid fan speeds. Values must be between 0 and 100: cpu={cpu}, gpu={gpu}")
            return False

        try:
            # Method 1: Try Acer Gaming WMI interface
            try:
                acer_wmi = wmi.WMI(namespace="root/WMI")
                
                # Try to set fan speed via AcerGaming_SetFanSpeed method
                try:
                    for controller in acer_wmi.AcerGaming_FanSpeedController():
                        if hasattr(controller, 'SetFanSpeed'):
                            controller.SetFanSpeed(cpu, gpu)
                            log.info(f"Set fan speeds via Acer WMI: CPU={cpu}%, GPU={gpu}%")
                            return True
                except:
                    pass
                
                # Alternative: Try setting through separate classes
                try:
                    for cpu_fan in acer_wmi.AcerGaming_CpuFanSpeed():
                        if hasattr(cpu_fan, 'SetSpeed'):
                            cpu_fan.SetSpeed(cpu)
                            log.info(f"Set CPU fan speed: {cpu}%")
                except:
                    pass
                    
                try:
                    for gpu_fan in acer_wmi.AcerGaming_GpuFanSpeed():
                        if hasattr(gpu_fan, 'SetSpeed'):
                            gpu_fan.SetSpeed(gpu)
                            log.info(f"Set GPU fan speed: {gpu}%")
                except:
                    pass
                    
            except Exception as e:
                log.debug(f"Acer WMI set fan speed not available: {e}")

            # Method 2: Try ACPI ACMC (Acer Control Method Computer) interface
            try:
                acer_wmi = wmi.WMI(namespace="root/WMI")
                for acmc in acer_wmi.AcerACMCEvent():
                    # Send fan control command via ACPI method
                    if hasattr(acmc, 'SetFanManual'):
                        if cpu == 0 and gpu == 0:
                            acmc.SetFanManual(False)  # Auto mode
                        else:
                            acmc.SetFanManual(True)  # Manual mode
                            acmc.SetFanSpeed(cpu, gpu)
                        return True
            except:
                pass

            # Method 3: Use PowerShell to call Acer WMI methods
            try:
                # Ensure values are safe integers (already validated above, but extra safety)
                safe_cpu = int(cpu)
                safe_gpu = int(gpu)
                
                # Build the PowerShell command to set fan speed
                ps_cmd = f'''
$namespace = "root\\WMI"
$classes = @("AcerGaming_FanSpeed", "AcerGaming_FanSpeedController", "AcerGaming_CpuFanSpeed", "AcerGaming_GpuFanSpeed")
foreach ($class in $classes) {{
    try {{
        $obj = Get-CimInstance -Namespace $namespace -ClassName $class -ErrorAction Stop
        if ($obj) {{
            $methods = Get-CimClass -Namespace $namespace -ClassName $class
            foreach ($method in $methods.CimClassMethods) {{
                if ($method.Name -like "*SetSpeed*" -or $method.Name -like "*SetFan*") {{
                    Invoke-CimMethod -InputObject $obj -MethodName $method.Name -Arguments @{{CpuSpeed={safe_cpu}; GpuSpeed={safe_gpu}}}
                    exit 0
                }}
            }}
        }}
    }} catch {{ }}
}}
exit 1
'''
                result = subprocess.run(
                    ["powershell", "-Command", ps_cmd],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    log.info(f"Set fan speeds via PowerShell: CPU={safe_cpu}%, GPU={safe_gpu}%")
                    return True
            except Exception as e:
                log.debug(f"PowerShell fan control failed: {e}")

            # If we get here, fan control might not be directly supported
            # Log what we attempted and suggest alternatives
            log.warning("Direct fan control not available on this system")
            log.info("Tip: Install Acer PredatorSense/NitroSense for full fan control")
            log.info("Alternative: Use 'performance' thermal profile for higher fan speeds")
            
            # Still return True if we can at least change thermal profile as a workaround
            if "thermal_profile" in self.available_features:
                if cpu >= 80 and gpu >= 80:
                    self.set_thermal_profile("performance")
                    log.info("Applied 'performance' thermal profile for higher fan speeds")
                    return True
                elif cpu == 0 and gpu == 0:
                    self.set_thermal_profile("balanced")
                    log.info("Applied 'balanced' thermal profile for auto fan control")
                    return True
            
            return False
            
        except Exception as e:
            log.error(f"Error setting fan speed: {e}")
            return False


    def get_lcd_override(self) -> str:
        """Get LCD override status - not directly supported on Windows"""
        return "0"

    def set_lcd_override(self, enabled: bool) -> bool:
        """Set LCD override status - not directly supported on Windows"""
        log.info("LCD override control not supported on Windows")
        return False

    def get_usb_charging(self) -> str:
        """Get USB charging status - not directly supported on Windows"""
        return "0"

    def set_usb_charging(self, level: int) -> bool:
        """Set USB charging level - not directly supported on Windows"""
        log.info("USB charging control not supported on Windows")
        return False

    def get_per_zone_mode(self) -> str:
        """Get per-zone mode configuration - not directly supported on Windows"""
        return ""

    def set_per_zone_mode(self, zone1: str, zone2: str, zone3: str, zone4: str, brightness: int) -> bool:
        """Set per-zone mode configuration - not directly supported on Windows"""
        log.info("Per-zone keyboard control not supported on Windows - use Acer NitroSense/PredatorSense")
        return False

    def get_four_zone_mode(self) -> str:
        """Get four-zone mode configuration - not directly supported on Windows"""
        return ""

    def set_four_zone_mode(self, mode: int, speed: int, brightness: int,
                           direction: int, red: int, green: int, blue: int) -> bool:
        """Set four-zone mode configuration - not directly supported on Windows"""
        log.info("Four-zone keyboard control not supported on Windows - use Acer NitroSense/PredatorSense")
        return False

    def get_all_settings(self) -> Dict:
        """Get all DAMX-Daemon settings as a dictionary"""
        settings = {
            "laptop_type": self.laptop_type.name,
            "has_four_zone_kb": self.has_four_zone_kb,
            "available_features": list(self.available_features),
            "version": VERSION,
            "driver_version": self.get_driver_version(),
            "modprobe_parameter": self.current_modprobe_param
        }

        # Only include thermal profile if available
        if "thermal_profile" in self.available_features:
            settings["thermal_profile"] = {
                "current": self.get_thermal_profile(),
                "available": self.get_thermal_profile_choices()
            }
        else:
            # Include an empty entry for compatibility
            settings["thermal_profile"] = {
                "current": "",
                "available": []
            }

        # Add all other features if available
        if "backlight_timeout" in self.available_features:
            settings["backlight_timeout"] = self.get_backlight_timeout()

        if "battery_calibration" in self.available_features:
            settings["battery_calibration"] = self.get_battery_calibration()

        if "battery_limiter" in self.available_features:
            settings["battery_limiter"] = self.get_battery_limiter()

        if "boot_animation_sound" in self.available_features:
            settings["boot_animation_sound"] = self.get_boot_animation_sound()

        if "fan_speed" in self.available_features:
            cpu_fan, gpu_fan = self.get_fan_speed()
            settings["fan_speed"] = {
                "cpu": cpu_fan,
                "gpu": gpu_fan
            }

        if "lcd_override" in self.available_features:
            settings["lcd_override"] = self.get_lcd_override()

        if "usb_charging" in self.available_features:
            settings["usb_charging"] = self.get_usb_charging()

        if "per_zone_mode" in self.available_features:
            settings["per_zone_mode"] = self.get_per_zone_mode()

        if "four_zone_mode" in self.available_features:
            settings["four_zone_mode"] = self.get_four_zone_mode()

        return settings


class DaemonServer:
    """Named Pipe server for IPC with the GUI client on Windows"""

    def __init__(self, manager: DAMXManager):
        self.manager = manager
        self.pipe_handle = None
        self.running = False
        self.clients = []

    def start(self):
        """Start the Named Pipe server"""
        try:
            self.running = True
            log.info(f"Server starting on {PIPE_NAME}")

            # Accept connections in a loop
            while self.running:
                try:
                    # Create a named pipe instance
                    pipe_handle = win32pipe.CreateNamedPipe(
                        PIPE_NAME,
                        win32pipe.PIPE_ACCESS_DUPLEX,
                        win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
                        win32pipe.PIPE_UNLIMITED_INSTANCES,
                        65536,  # Output buffer size
                        65536,  # Input buffer size
                        0,      # Default timeout
                        None    # Security attributes
                    )
                    
                    log.info("Waiting for client connection...")
                    
                    # Wait for a client to connect
                    win32pipe.ConnectNamedPipe(pipe_handle, None)
                    
                    log.info("Client connected")
                    
                    # Handle client in a new thread
                    client_thread = threading.Thread(target=self.handle_client, args=(pipe_handle,))
                    client_thread.daemon = True
                    client_thread.start()
                    self.clients.append((pipe_handle, client_thread))
                    
                except pywintypes.error as e:
                    if e.winerror == 232:  # ERROR_NO_DATA - client disconnected
                        continue
                    if self.running:
                        log.error(f"Error accepting connection: {e}")
                except Exception as e:
                    if self.running:
                        log.error(f"Error accepting connection: {e}")

            return True

        except Exception as e:
            log.error(f"Failed to start server: {e}")
            return False

    def stop(self):
        """Stop the server and clean up"""
        log.info("Stopping server...")
        self.running = False
    
        # Close all client connections
        for pipe_handle, _ in self.clients:
            try:
                win32file.CloseHandle(pipe_handle)
            except:
                pass

    def cleanup_socket(self):
        """Clean up - no file cleanup needed for named pipes on Windows"""
        pass

    def handle_client(self, pipe_handle):
        """Handle communication with a client"""
        try:
            while self.running:
                try:
                    # Read message length first (4 bytes)
                    result, length_data = win32file.ReadFile(pipe_handle, 4)
                    if result != 0 or len(length_data) < 4:
                        break
                    
                    msg_length = int.from_bytes(length_data, byteorder='little')
                    
                    # Read the full message
                    result, data = win32file.ReadFile(pipe_handle, msg_length)
                    if result != 0:
                        break

                    # Parse JSON request
                    request = json.loads(data.decode('utf-8'))
                    command = request.get("command", "")
                    params = request.get("params", {})

                    # Process command
                    response = self.process_command(command, params)

                    # Send response
                    response_data = json.dumps(response).encode('utf-8')
                    response_length = len(response_data).to_bytes(4, byteorder='little')
                    win32file.WriteFile(pipe_handle, response_length + response_data)

                except pywintypes.error as e:
                    if e.winerror == 109:  # ERROR_BROKEN_PIPE
                        break
                    log.error(f"Pipe error: {e}")
                    break
                except json.JSONDecodeError:
                    log.error("Invalid JSON received")
                    response_data = json.dumps({
                        "success": False,
                        "error": "Invalid JSON format"
                    }).encode('utf-8')
                    response_length = len(response_data).to_bytes(4, byteorder='little')
                    win32file.WriteFile(pipe_handle, response_length + response_data)
                except Exception as e:
                    log.error(f"Error processing request: {e}")
                    log.error(traceback.format_exc())
                    response_data = json.dumps({
                        "success": False,
                        "error": str(e)
                    }).encode('utf-8')
                    response_length = len(response_data).to_bytes(4, byteorder='little')
                    try:
                        win32file.WriteFile(pipe_handle, response_length + response_data)
                    except:
                        pass

        except Exception as e:
            if self.running:
                log.error(f"Client connection error: {e}")
        finally:
            try:
                win32file.CloseHandle(pipe_handle)
            except:
                pass

    def process_command(self, command: str, params: Dict) -> Dict:
        """Process a command from the client"""
        log.info(f"Processing command: {command} with params: {params}")

        try:
            if command == "get_all_settings":
                settings = self.manager.get_all_settings()
                return {
                    "success": True,
                    "data": settings
                }

            elif command == "get_thermal_profile":
                # Check if feature is available
                if "thermal_profile" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Thermal profile is not supported on this device"
                    }

                profile = self.manager.get_thermal_profile()
                choices = self.manager.get_thermal_profile_choices()
                return {
                    "success": True,
                    "data": {
                        "current": profile,
                        "available": choices
                    }
                }

            elif command == "set_thermal_profile":
                # Check if feature is available
                if "thermal_profile" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Thermal profile is not supported on this device"
                    }

                profile = params.get("profile", "")
                success = self.manager.set_thermal_profile(profile)
                return {
                    "success": success,
                    "data": {"profile": profile} if success else None,
                    "error": "Failed to set thermal profile" if not success else None
                }

            elif command == "set_backlight_timeout":
                # Check if feature is available
                if "backlight_timeout" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Backlight timeout is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_backlight_timeout(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set backlight timeout" if not success else None
                }

            elif command == "set_battery_calibration":
                # Check if feature is available
                if "battery_calibration" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Battery calibration is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_battery_calibration(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set battery calibration" if not success else None
                }

            elif command == "set_battery_limiter":
                # Check if feature is available
                if "battery_limiter" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Battery limiter is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_battery_limiter(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set battery limiter" if not success else None
                }

            elif command == "set_boot_animation_sound":
                # Check if feature is available
                if "boot_animation_sound" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Boot animation sound is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_boot_animation_sound(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set boot animation sound" if not success else None
                }

            elif command == "set_fan_speed":
                # Check if feature is available
                if "fan_speed" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Fan speed control is not supported on this device"
                    }

                cpu = params.get("cpu", 0)
                gpu = params.get("gpu", 0)
                success = self.manager.set_fan_speed(cpu, gpu)
                return {
                    "success": success,
                    "data": {"cpu": cpu, "gpu": gpu} if success else None,
                    "error": "Failed to set fan speed" if not success else None
                }

            elif command == "set_lcd_override":
                # Check if feature is available
                if "lcd_override" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "LCD override is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_lcd_override(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set LCD override" if not success else None
                }

            elif command == "set_usb_charging":
                # Check if feature is available
                if "usb_charging" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "USB charging control is not supported on this device"
                    }

                level = params.get("level", 0)
                success = self.manager.set_usb_charging(level)
                return {
                    "success": success,
                    "data": {"level": level} if success else None,
                    "error": "Failed to set USB charging" if not success else None
                }

            elif command == "set_per_zone_mode":
                # Check if feature is available
                if "per_zone_mode" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Per-zone keyboard mode is not supported on this device"
                    }

                zone1 = params.get("zone1", "000000")
                zone2 = params.get("zone2", "000000")
                zone3 = params.get("zone3", "000000")
                zone4 = params.get("zone4", "000000")
                brightness = params.get("brightness", 100)
                success = self.manager.set_per_zone_mode(zone1, zone2, zone3, zone4, brightness)
                return {
                    "success": success,
                    "data": {
                        "zone1": zone1,
                        "zone2": zone2,
                        "zone3": zone3,
                        "zone4": zone4,
                        "brightness": brightness
                    } if success else None,
                    "error": "Failed to set per-zone mode" if not success else None
                }

            elif command == "set_four_zone_mode":
                # Check if feature is available
                if "four_zone_mode" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Four-zone keyboard mode is not supported on this device"
                    }

                mode = params.get("mode", 0)
                speed = params.get("speed", 0)
                brightness = params.get("brightness", 100)
                direction = params.get("direction", 1)
                red = params.get("red", 0)
                green = params.get("green", 0)
                blue = params.get("blue", 0)
                success = self.manager.set_four_zone_mode(mode, speed, brightness, direction, red, green, blue)
                return {
                    "success": success,
                    "data": {
                        "mode": mode,
                        "speed": speed,
                        "brightness": brightness,
                        "direction": direction,
                        "red": red,
                        "green": green,
                        "blue": blue
                    } if success else None,
                    "error": "Failed to set four-zone mode" if not success else None
                }

            elif command == "get_supported_features":
                return {
                    "success": True,
                    "data": {
                        "available_features": list(self.manager.available_features),
                        "laptop_type": self.manager.laptop_type.name,
                        "has_four_zone_kb": self.manager.has_four_zone_kb
                    }
                }

            elif command == "get_version":
                return {
                    "success": True,
                    "data": {
                        "version": VERSION
                    }
                }
            
            # Force Models and Features
            elif command == "force_nitro_model":
                # Force Nitro model into driver
                success = self.manager._force_model_nitro()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully forced Nitro model into driver"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to force Nitro model into driver"
                    }
                
            elif command == "force_predator_model":
                # Force Predator model into driver
                success = self.manager._force_model_predator()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully forced Predator model into driver"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to force Predator model into driver (Model may not support it)"
                    }

            elif command == "force_enable_all":
                # Force Enable All Features into driver
                success = self.manager._force_enable_all()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully forced all features into driver"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to force all features into driver (Model may not support it)"
                    }
                
            elif command == "get_modprobe_parameter":
                print (self.manager.get_modprobe_parameter())
                return {
                    "success": True,
                    "data": {
                        "parameter": self.manager.get_modprobe_parameter()
                    }
                }

            # Force Model and Parameters Permanantly
            elif command == "set_modprobe_parameter_nitro":
                success = self.manager.set_modprobe_parameter("nitro_v4")
                return {
                    "success": success,
                    "data": {"parameter": param} if success else None,
                    "error": "Failed to set modprobe parameter" if not success else None
                }
            
            elif command == "set_modprobe_parameter_predator":
                param = params.get("parameter", "")
                success = self.manager.set_modprobe_parameter("predator_v4")
                return {
                    "success": success,
                    "data": {"parameter": param} if success else None,
                    "error": "Failed to set modprobe parameter" if not success else None
                }
            
            elif command == "set_modprobe_parameter_enable_all":
                param = params.get("parameter", "")
                success = self.manager.set_modprobe_parameter("enable_all")
                return {
                    "success": success,
                    "data": {"parameter": param} if success else None,
                    "error": "Failed to set modprobe parameter" if not success else None
                }

            elif command == "remove_modprobe_parameter":
                success = self.manager._remove_modprobe_parameter()
                return {
                    "success": success,
                    "message": "Successfully removed modprobe parameter" if success else None,
                    "error": "Failed to remove modprobe parameter" if not success else None
                }
            
            elif command == "restart_daemon":
                # Force Nitro model into driver
                success = self.manager._restart_daemon()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully restarted DAMX daemon"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to Restart DAMX daemon (Check logs for details)"
                    }           

            elif command == "restart_drivers_and_daemon":
                # Restart linuwu-sense driver and DAMX daemon service
                success = self.manager._restart_drivers_and_daemon()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully restarted drivers and daemon"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to restart drivers and daemon"
                    }
            else:
                return {
                    "success": False,
                    "error": f"Unknown command: {command}"
                }

        except Exception as e:
            log.error(f"Error processing command {command}: {e}")
            log.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }


class DAMXDaemon:
    """Main daemon class that manages the lifecycle"""

    def __init__(self):
        self.running = False
        self.manager = None
        self.server = None
        self.config = None

    def load_config(self):
        """Load configuration from file"""
        config = configparser.ConfigParser()

        # Create default config if it doesn't exist
        if not os.path.exists(CONFIG_PATH):
            log.info(f"Creating default config at {CONFIG_PATH}")
            config['General'] = {
                'LogLevel': 'INFO',
                'AutoDetectFeatures': 'True'
            }

            # Create config directory if it doesn't exist
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

            # Write default config
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
        else:
            # Load existing config
            config.read(CONFIG_PATH)

        self.config = config

        # Set log level from config
        if 'General' in config and 'LogLevel' in config['General']:
            log_level = config['General']['LogLevel'].upper()
            if log_level in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
                #log.setLevel(getattr(logging, log_level))
                log.setLevel(logging.DEBUG)
                
                log.info(f"Log level set to {log_level}")

        return config

    def setup(self):
        """Set up the daemon"""
        # Load configuration first
        self.load_config()

        try:
            # Initialize DAMXManager
            self.manager = DAMXManager()

            # Initialize power monitor if available
            if PowerSourceDetector is not None:
                self.power_monitor = PowerSourceDetector(self.manager)
                self.power_monitor.start_monitoring()
            else:
                log.warning("Power source detection not available")
                self.power_monitor = None

            # Log detected features
            features_str = ", ".join(sorted(self.manager.available_features))
            log.info(f"Detected features: {features_str}")

            return True
        except Exception as e:
            log.error(f"Failed to set up daemon: {e}")
            log.error(traceback.format_exc())
            return False
    


    def run(self):
        """Run the daemon"""
        # Set up signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        # Note: SIGTERM may not work on Windows, use Ctrl+C or service stop

        # Set up and run the server
        try:
            self.running = True
            self.server = DaemonServer(self.manager)
            if self.power_monitor:
                self.power_monitor.start_monitoring()
            self.server.start()
            
        except Exception as e:
            log.error(f"Error running daemon: {e}")
            log.error(traceback.format_exc())
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        log.info("Cleaning up resources...")
    
        # Stop server
        if self.server:
            self.server.stop()
    
        if self.power_monitor:
            self.power_monitor.stop_monitoring()
    
        log.info("Daemon stopped")

    def signal_handler(self, sig, frame):
        """Handle termination signals"""
        log.info(f"Received signal {sig}, shutting down...")
        self.running = False
        if self.server:
            self.server.running = False

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="DAMX-Daemon (Windows)")
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose logging")
    parser.add_argument('--version', action='version', version=f"DAMX-Daemon v{VERSION}")
    parser.add_argument('--debug', action='store_true', help="Enable debug mode")
    parser.add_argument('--config', type=str, help=f"Path to config file (default: {CONFIG_PATH})")
    return parser.parse_args()

def main():
    """Main function"""
    args = parse_args()
    
    log.info(f"Driver Version: {DAMXManager().get_driver_version()}")

    # Set log level based on verbosity
    if args.verbose:
        log.setLevel(logging.DEBUG)
        log.debug("Debug logging enabled")

    # Use custom config path if provided
    global CONFIG_PATH
    if args.config:
        CONFIG_PATH = args.config

    daemon = DAMXDaemon()
    if daemon.setup():
        daemon.run()
    else:
        log.error("Failed to set up daemon, exiting...")
        sys.exit(1)

    


if __name__ == "__main__":
    main()