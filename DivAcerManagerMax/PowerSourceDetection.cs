using System;
using System.Management;
using System.Timers;
using Avalonia.Controls;
using Avalonia.Threading;

public class PowerSourceDetection
{
    private readonly Timer _powerSourceCheckTimer;
    private readonly ToggleSwitch _powerToggleSwitch;

    public PowerSourceDetection(ToggleSwitch powerToggleSwitch)
    {
        _powerToggleSwitch = powerToggleSwitch;

        // Initialize and start the timer to check power source every 5 seconds
        _powerSourceCheckTimer = new Timer(5000);
        _powerSourceCheckTimer.Elapsed += OnTimerElapsed;
        _powerSourceCheckTimer.AutoReset = true;
        _powerSourceCheckTimer.Start();

        // Initial check of power source
        UpdatePowerSourceStatus();
    }

    private void OnTimerElapsed(object? sender, ElapsedEventArgs e)
    {
        UpdatePowerSourceStatus();
    }

    private void UpdatePowerSourceStatus()
    {
        var isPluggedIn = IsLaptopPluggedIn();

        // Update UI on UI thread
        Dispatcher.UIThread.InvokeAsync(() => { _powerToggleSwitch.IsChecked = isPluggedIn; });
    }

    private bool IsLaptopPluggedIn()
    {
        try
        {
            // Use WMI to check power status on Windows
            using var searcher = new ManagementObjectSearcher("SELECT * FROM Win32_Battery");
            foreach (ManagementObject battery in searcher.Get())
            {
                var batteryStatus = battery["BatteryStatus"];
                if (batteryStatus != null)
                {
                    // BatteryStatus values:
                    // 1 = Discharging, 2 = AC connected (not charging), 
                    // 3 = Fully Charged, 4 = Low, 5 = Critical,
                    // 6 = Charging, 7 = Charging and High, 8 = Charging and Low,
                    // 9 = Charging and Critical, 10 = Undefined, 11 = Partially Charged
                    var status = Convert.ToInt32(batteryStatus);
                    return status != 1 && status != 4 && status != 5; // Not on battery power
                }
            }

            // Fallback: Check using SystemInformation
            return CheckUsingSystemPowerStatus();
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error checking power status: {ex.Message}");
            return false;
        }
    }

    private bool CheckUsingSystemPowerStatus()
    {
        try
        {
            // Use System.Windows.Forms or P/Invoke for GetSystemPowerStatus
            // For simplicity, use WMI as primary method
            using var searcher = new ManagementObjectSearcher("SELECT * FROM Win32_PowerMeter");
            foreach (ManagementObject meter in searcher.Get())
            {
                // If we have any power meter reading, we're likely plugged in
                return true;
            }
        }
        catch
        {
            // WMI query failed, assume battery power
        }

        return false;
    }
}