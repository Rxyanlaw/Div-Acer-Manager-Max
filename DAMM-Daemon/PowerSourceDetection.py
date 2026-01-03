#!/usr/bin/env python3
# DAMX Power Source Detection - Monitors power source and adjusts thermal profiles accordingly
# Windows version using WMI

import logging
import subprocess
from threading import Timer

# Get logger from main daemon
log = logging.getLogger("DAMXDaemon")

class PowerSourceDetector:
    """Detects power source and manages automatic mode switching on Windows"""

    def __init__(self, manager):
        self.manager = manager
        self.current_source = None
        self.check_interval = 5  # seconds
        self.timer = None
        
        log.info("PowerSourceDetector initialized (Windows)")

    def start_monitoring(self):
        """Start periodic power source checking"""
        self.check_power_source()
        log.info("Monitoring power source started")

    def stop_monitoring(self):
        """Stop periodic power source checking"""
        if self.timer:
            self.timer.cancel()

    def check_power_source(self):
        """Check current power source and adjust settings if needed"""
        is_plugged_in = self._is_ac_connected()

        # Only take action if power state changed
        if is_plugged_in != self.current_source:
            self.current_source = is_plugged_in
            self._handle_power_change(is_plugged_in)

        # Schedule next check
        self.timer = Timer(self.check_interval, self.check_power_source)
        self.timer.daemon = True
        self.timer.start()

    def _is_ac_connected(self) -> bool:
        """Check if AC power is connected using WMI"""
        try:
            import wmi
            c = wmi.WMI()
            
            for battery in c.Win32_Battery():
                # BatteryStatus: 1 = Discharging, 2+ = Charging/AC
                status = battery.BatteryStatus
                if status and status != 1:
                    return True
                return False
            
            # No battery found, assume desktop (always on AC)
            return True
            
        except ImportError:
            # WMI not available, try powershell fallback
            return self._check_using_powershell()
        except Exception as e:
            log.error(f"Error checking power status: {e}")
            return False

    def _check_using_powershell(self) -> bool:
        """Check power status using PowerShell"""
        try:
            result = subprocess.run(
                ["powershell", "-Command", 
                 "(Get-WmiObject Win32_Battery).BatteryStatus"],
                capture_output=True,
                text=True,
                check=True
            )
            status = result.stdout.strip()
            # Status 1 = discharging (on battery), anything else = on AC
            return status != "1"
        except Exception as e:
            log.error(f"PowerShell check failed: {e}")
            return False

    def _handle_power_change(self, is_plugged_in: bool):
        """Handle power source changes"""
        if not hasattr(self.manager, 'available_features') or "thermal_profile" not in self.manager.available_features:
            return

        current_profile = self.manager.get_thermal_profile()
        available_profiles = self.manager.get_thermal_profile_choices()

        if is_plugged_in:
            # On AC power - no restrictions
            log.info("Switched to AC power")
        else:
            # On battery power - enforce balanced or eco mode
            log.info("Switched to battery power")

            if current_profile not in ["balanced", "quiet", "low-power"]:
                # If current profile isn't battery-friendly, switch to balanced
                if "balanced" in available_profiles:
                    log.info("Auto-switching to balanced mode for battery power")
                    self.manager.set_thermal_profile("balanced")
                elif "quiet" in available_profiles:
                    log.info("Auto-switching to quiet mode for battery power")
                    self.manager.set_thermal_profile("quiet")
                elif "low-power" in available_profiles:
                    log.info("Auto-switching to low-power mode for battery power")
                    self.manager.set_thermal_profile("low-power")
                else:
                    log.warning("No battery-friendly thermal profile available")