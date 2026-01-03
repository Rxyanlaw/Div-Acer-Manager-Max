using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Management;
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Avalonia.Animation;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Styling;
using Avalonia.Threading;
using LiveChartsCore;
using LiveChartsCore.SkiaSharpView;
using LiveChartsCore.SkiaSharpView.Avalonia;
using LiveChartsCore.SkiaSharpView.Painting;
using Material.Icons.Avalonia;
using SkiaSharp;

namespace DivAcerManagerMax;

public partial class Dashboard : UserControl, INotifyPropertyChanged
{
    private const int REFRESH_INTERVAL_MS = 2000; // 2 seconds
    private const int MAX_HISTORY_POINTS = 60; // 1 minute of history (30 * 2s refresh)

    private const int MIN_RPM_FOR_ANIMATION = 100;
    private const double MAX_ANIMATION_DURATION = 5.0; // seconds for very slow rotation
    private const double MIN_ANIMATION_DURATION = 0.05; // seconds for very fast rotation
    private const int RPM_CHANGE_THRESHOLD = 500; // Only update animation if RPM changes by this much
    private readonly RotateTransform _cpuFanRotateTransform;
    private readonly RotateTransform _gpuFanRotateTransform;

    // Timer to refresh dynamic system metrics
    private readonly DispatcherTimer _refreshTimer;

    // Cache for system info paths
    private readonly Dictionary<string, string> _systemInfoPaths = new();

    private bool _animationsInitialized;
    private string? _batteryDir;
    private int _batteryPercentageInt;
    private string _batteryStatus;
    private string _batteryTimeRemainingString;
    private Animation? _cpuFanAnimation;
    private int _cpuFanSpeedRpm;
    private string _cpuName;
    private double _cpuTemp;
    private ObservableCollection<double> _cpuTempHistory;
    private double _cpuUsage;

    public bool _fanPathsSearched;
    private Animation? _gpuFanAnimation;
    private int _gpuFanSpeedRpm;
    private string _gpuName;
    private double _gpuTemp;
    private ObservableCollection<double> _gpuTempHistory;
    private GpuType _gpuType = GpuType.Unknown;
    private double _gpuUsage;
    private bool _hasBattery;
    private string _kernelVersion;
    private int _lastCpuRpm;
    private int _lastGpuRpm;
    private string _osVersion;
    private string _ramTotal;
    private double _ramUsage;
    private CartesianChart _temperatureChart;
    private ObservableCollection<ISeries> _tempSeries;

    public Dashboard()
    {
        InitializeComponent();
        DataContext = this;

        // Initialize rotate transforms
        _cpuFanRotateTransform = new RotateTransform();
        _gpuFanRotateTransform = new RotateTransform();

        // Initialize default values for battery properties
        BatteryPercentage.Text = "0";
        BatteryTimeRemaining.Text = "0";
        BatteryStatus = "Unknown";

        // Fetch static system information once at initialization
        InitializeStaticSystemInfo();

        // Setup refresh timer for dynamic metrics
        _refreshTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromMilliseconds(REFRESH_INTERVAL_MS)
        };
        _refreshTimer.Tick += RefreshDynamicMetrics;
        _refreshTimer.Start();

        // Initial refresh of dynamic metrics
        RefreshDynamicMetricsAsync();
    }

    public string CpuName
    {
        get => _cpuName;
        set => SetProperty(ref _cpuName, value);
    }

    public string GpuName
    {
        get => _gpuName;
        set => SetProperty(ref _gpuName, value);
    }

    public int CpuFanSpeedRPM
    {
        get => _cpuFanSpeedRpm;
        set => SetProperty(ref _cpuFanSpeedRpm, value);
    }

    public int GpuFanSpeedRPM
    {
        get => _gpuFanSpeedRpm;
        set => SetProperty(ref _gpuFanSpeedRpm, value);
    }

    public string OsVersion
    {
        get => _osVersion;
        set => SetProperty(ref _osVersion, value);
    }

    public string KernelVersion
    {
        get => _kernelVersion;
        set => SetProperty(ref _kernelVersion, value);
    }

    public string RamTotal
    {
        get => _ramTotal;
        set => SetProperty(ref _ramTotal, value);
    }

    public double CpuTemp
    {
        get => _cpuTemp;
        set => SetProperty(ref _cpuTemp, value);
    }

    public double GpuTemp
    {
        get => _gpuTemp;
        set => SetProperty(ref _gpuTemp, value);
    }

    public double CpuUsage
    {
        get => _cpuUsage;
        set => SetProperty(ref _cpuUsage, value);
    }

    public double RamUsage
    {
        get => _ramUsage;
        set => SetProperty(ref _ramUsage, value);
    }

    public double GpuUsage
    {
        get => _gpuUsage;
        set => SetProperty(ref _gpuUsage, value);
    }

    public string BatteryStatus
    {
        get => _batteryStatus;
        set => SetProperty(ref _batteryStatus, value);
    }

    public int BatteryPercentageInt
    {
        get => _batteryPercentageInt;
        set => SetProperty(ref _batteryPercentageInt, value);
    }

    public string BatteryTimeRemainingString
    {
        get => _batteryTimeRemainingString;
        set => SetProperty(ref _batteryTimeRemainingString, value);
    }

    public bool HasBattery
    {
        get => _hasBattery;
        set => SetProperty(ref _hasBattery, value);
    }

    // INotifyPropertyChanged implementation
    public event PropertyChangedEventHandler? PropertyChanged;

    private void RefreshDynamicMetrics(object? sender, EventArgs e)
    {
        RefreshDynamicMetricsAsync();
    }

    private async void RefreshDynamicMetricsAsync()
    {
        try
        {
            var metricsData = await Task.Run(() =>
            {
                var data = new MetricsData();

                // Update CPU metrics
                data.CpuUsage = GetCpuUsage();
                data.CpuTemp = GetCpuTemperature();

                // Update fan metrics - now using cached paths
                var fanSpeeds = GetFanSpeeds();
                data.CpuFanSpeedRPM = fanSpeeds.cpuFan;
                data.GpuFanSpeedRPM = fanSpeeds.gpuFan;

                // Update RAM metrics
                data.RamUsage = GetRamUsage();

                // Update GPU metrics
                var gpuMetrics = GetGpuMetrics();
                data.GpuTemp = gpuMetrics.temperature;
                data.GpuUsage = gpuMetrics.usage;

                // Update battery metrics
                var batteryInfo = GetBatteryInfo();
                data.BatteryPercentage = batteryInfo.percentage;
                data.BatteryStatus = batteryInfo.status;
                data.BatteryTimeRemaining = $"{batteryInfo.timeRemaining:F2} hours";
                return data;
            });

            // Update UI from UI thread
            Dispatcher.UIThread.Post(() =>
            {
                // Apply the collected metrics to UI-bound properties
                CpuUsage = metricsData.CpuUsage;
                CpuTemp = metricsData.CpuTemp;
                RamUsage = metricsData.RamUsage;
                GpuTemp = metricsData.GpuTemp;
                GpuUsage = metricsData.GpuUsage;
                BatteryPercentageInt = metricsData.BatteryPercentage;
                BatteryStatus = metricsData.BatteryStatus;
                BatteryTimeRemaining.Text = metricsData.BatteryTimeRemaining;
                BatteryLevelBar.Value = metricsData.BatteryPercentage;

                CpuFanSpeed.Text = $"{metricsData.CpuFanSpeedRPM} RPM";
                GpuFanSpeed.Text = $"{metricsData.GpuFanSpeedRPM} RPM";
                UpdateFanAnimations();

                // Update temperature history charts
                if (_cpuTempHistory.Count >= MAX_HISTORY_POINTS)
                    _cpuTempHistory.RemoveAt(0);
                _cpuTempHistory.Add(metricsData.CpuTemp);

                if (_gpuTempHistory.Count >= MAX_HISTORY_POINTS)
                    _gpuTempHistory.RemoveAt(0);
                _gpuTempHistory.Add(metricsData.GpuTemp);
            });
        }
        catch (Exception ex)
        {
            // Log exception if needed
            Console.WriteLine($"Error updating metrics: {ex.Message}");
        }
    }

    private void InitializeStaticSystemInfo()
    {
        try
        {
            // Initialize CPU information
            CpuName = GetCpuName();

            // Initialize GPU information
            DetectGpuType();
            GpuName = GetGpuName();

            // Find fan speed paths and cache them
            FindSystemPaths();

            // Update GPU driver info on UI thread
            var gpuDriver = GetGpuDriverVersion();

            // Initialize temperature graph
            InitializeTemperatureGraph();

            Dispatcher.UIThread.Post(() => { GpuDriver.Text = gpuDriver; });

            // Get OS information
            OsVersion = GetOsVersion();
            KernelVersion = GetKernelVersion();

            // Get RAM information
            RamTotal = GetTotalRam();

            // Check if system has a battery and find its directory
            CheckForBattery();
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error during initialization: {ex.Message}");
        }
    }

    private string GetCpuName()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT Name FROM Win32_Processor");
            foreach (ManagementObject processor in searcher.Get())
            {
                var name = processor["Name"]?.ToString();
                if (!string.IsNullOrEmpty(name))
                    return name.Trim();
            }
            return "Unknown CPU";
        }
        catch
        {
            return "CPU Information Unavailable";
        }
    }

    private void DetectGpuType()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT Name FROM Win32_VideoController");
            foreach (ManagementObject gpu in searcher.Get())
            {
                var name = gpu["Name"]?.ToString()?.ToUpper() ?? "";
                
                if (name.Contains("NVIDIA"))
                {
                    _gpuType = GpuType.Nvidia;
                    return;
                }
                if (name.Contains("AMD") || name.Contains("RADEON"))
                {
                    _gpuType = GpuType.Amd;
                    return;
                }
                if (name.Contains("INTEL"))
                {
                    _gpuType = GpuType.Intel;
                    return;
                }
            }

            _gpuType = GpuType.Unknown;
        }
        catch
        {
            _gpuType = GpuType.Unknown;
        }
    }

    private string GetGpuName()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT Name FROM Win32_VideoController");
            foreach (ManagementObject gpu in searcher.Get())
            {
                var name = gpu["Name"]?.ToString();
                if (!string.IsNullOrEmpty(name))
                    return name.Trim();
            }
            return "Unknown GPU";
        }
        catch
        {
            return "GPU Information Unavailable";
        }
    }

    private string GetGpuDriverVersion()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT DriverVersion FROM Win32_VideoController");
            foreach (ManagementObject gpu in searcher.Get())
            {
                var driverVersion = gpu["DriverVersion"]?.ToString();
                if (!string.IsNullOrEmpty(driverVersion))
                    return driverVersion.Trim();
            }
            return "Unknown Driver";
        }
        catch
        {
            return "Driver Information Unavailable";
        }
    }

    private string GetOsVersion()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT Caption, Version FROM Win32_OperatingSystem");
            foreach (ManagementObject os in searcher.Get())
            {
                var caption = os["Caption"]?.ToString() ?? "Windows";
                var version = os["Version"]?.ToString() ?? "";
                return $"{caption} ({version})".Trim();
            }
            return "Unknown Windows Version";
        }
        catch
        {
            return "OS Information Unavailable";
        }
    }

    private string GetKernelVersion()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT Version FROM Win32_OperatingSystem");
            foreach (ManagementObject os in searcher.Get())
            {
                var version = os["Version"]?.ToString();
                if (!string.IsNullOrEmpty(version))
                    return version.Trim();
            }
            return Environment.OSVersion.Version.ToString();
        }
        catch
        {
            return "Version Information Unavailable";
        }
    }

    private string GetTotalRam()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT TotalPhysicalMemory FROM Win32_ComputerSystem");
            foreach (ManagementObject system in searcher.Get())
            {
                var totalMemory = system["TotalPhysicalMemory"];
                if (totalMemory != null)
                {
                    var bytes = Convert.ToInt64(totalMemory);
                    var gbytes = bytes / (1024.0 * 1024.0 * 1024.0);
                    return $"{gbytes:F2} GB";
                }
            }
            return "Unknown";
        }
        catch
        {
            return "RAM Information Unavailable";
        }
    }

    private void CheckForBattery()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT * FROM Win32_Battery");
            var batteries = searcher.Get().Cast<ManagementObject>().ToList();
            HasBattery = batteries.Any();
            
            if (HasBattery)
            {
                _batteryDir = "WMI"; // Marker indicating we use WMI
            }
        }
        catch (Exception ex)
        {
            HasBattery = false;
            Console.WriteLine($"Error checking battery: {ex.Message}");
        }
    }

    private void InitializeTemperatureGraph()
    {
        // Initialize collections
        _cpuTempHistory = new ObservableCollection<double>();
        _gpuTempHistory = new ObservableCollection<double>();

        // Initialize series
        _tempSeries = new ObservableCollection<ISeries>
        {
            new LineSeries<double>
            {
                Values = _cpuTempHistory,
                Name = "CPU Temperature",
                Stroke = new SolidColorPaint(SKColors.CornflowerBlue) { StrokeThickness = 3 },
                GeometryStroke = new SolidColorPaint(SKColors.DeepSkyBlue),
                GeometryFill = new SolidColorPaint(SKColors.DeepSkyBlue),
                Fill = new SolidColorPaint(SKColors.Transparent),
                GeometrySize = 5,
                XToolTipLabelFormatter = chartPoint => $"CPU: {chartPoint.Label}°C"
            },
            new LineSeries<double>
            {
                Values = _gpuTempHistory,
                Name = "GPU Temperature",
                Stroke = new SolidColorPaint(SKColors.LimeGreen) { StrokeThickness = 3 },
                GeometryFill = new SolidColorPaint(SKColors.GreenYellow),
                GeometryStroke = new SolidColorPaint(SKColors.GreenYellow),
                Fill = new SolidColorPaint(SKColors.Transparent),
                GeometrySize = 5,
                XToolTipLabelFormatter = chartPoint => $"GPU: {chartPoint.Label}°C"
            }
        };

        // Initialize and configure the chart
        _temperatureChart = this.FindControl<CartesianChart>("TemperatureChart");
        if (_temperatureChart != null)
        {
            _temperatureChart.Series = _tempSeries;
            _temperatureChart.XAxes = new List<Axis>
            {
                new()
                {
                    Name = "Time",
                    IsVisible = false
                }
            };
            _temperatureChart.YAxes = new List<Axis>
            {
                new()
                {
                    Name = "Temperature (°C)",
                    NamePaint = new SolidColorPaint(SKColors.Gray),
                    LabelsPaint = new SolidColorPaint(SKColors.Gray)
                }
            };
        }
    }

    private double GetCpuUsage()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT LoadPercentage FROM Win32_Processor");
            var totalLoad = 0.0;
            var count = 0;
            foreach (ManagementObject processor in searcher.Get())
            {
                var load = processor["LoadPercentage"];
                if (load != null)
                {
                    totalLoad += Convert.ToDouble(load);
                    count++;
                }
            }
            return count > 0 ? Math.Round(totalLoad / count, 1) : 0;
        }
        catch
        {
            return 0;
        }
    }

    private double GetCpuTemperature()
    {
        try
        {
            // Try to get CPU temperature using WMI (MSAcpi_ThermalZoneTemperature)
            // Note: This requires admin privileges on Windows
            try
            {
                using var searcher = new ManagementObjectSearcher(@"root\WMI", "SELECT * FROM MSAcpi_ThermalZoneTemperature");
                foreach (ManagementObject temp in searcher.Get())
                {
                    var currentTemp = temp["CurrentTemperature"];
                    if (currentTemp != null)
                    {
                        // Temperature is in tenths of Kelvin, convert to Celsius
                        var kelvinTenths = Convert.ToDouble(currentTemp);
                        var celsius = (kelvinTenths / 10.0) - 273.15;
                        return Math.Round(celsius, 1);
                    }
                }
            }
            catch (ManagementException)
            {
                // MSAcpi_ThermalZoneTemperature may require admin privileges
            }
            
            // Fallback: Try Open Hardware Monitor WMI (if installed)
            try
            {
                using var ohmSearcher = new ManagementObjectSearcher(@"root\OpenHardwareMonitor", 
                    "SELECT * FROM Sensor WHERE SensorType='Temperature' AND Name LIKE '%CPU%'");
                foreach (ManagementObject sensor in ohmSearcher.Get())
                {
                    var value = sensor["Value"];
                    if (value != null)
                        return Math.Round(Convert.ToDouble(value), 1);
                }
            }
            catch { /* Open Hardware Monitor not installed */ }

            return 0;
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error getting CPU temperature: {ex.Message}");
            return 0;
        }
    }

    private double GetRamUsage()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT TotalPhysicalMemory FROM Win32_ComputerSystem");
            long totalMemory = 0;
            foreach (ManagementObject system in searcher.Get())
            {
                var total = system["TotalPhysicalMemory"];
                if (total != null)
                    totalMemory = Convert.ToInt64(total);
            }

            using var perfSearcher = new ManagementObjectSearcher("SELECT AvailableBytes FROM Win32_PerfFormattedData_PerfOS_Memory");
            long availableMemory = 0;
            foreach (ManagementObject mem in perfSearcher.Get())
            {
                var available = mem["AvailableBytes"];
                if (available != null)
                    availableMemory = Convert.ToInt64(available);
            }

            if (totalMemory > 0)
            {
                var usedMemory = totalMemory - availableMemory;
                var usagePercentage = (usedMemory / (double)totalMemory) * 100.0;
                return Math.Round(usagePercentage, 1);
            }

            return 0;
        }
        catch
        {
            return 0;
        }
    }

    private (double temperature, double usage) GetGpuMetrics()
    {
        try
        {
            double temp = 0;
            double usage = 0;

            // Try NVIDIA nvidia-smi first (works on Windows)
            if (_gpuType == GpuType.Nvidia)
            {
                var nvidiaSmiOutput = RunCommand("nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu --format=csv,noheader,nounits");
                if (!string.IsNullOrWhiteSpace(nvidiaSmiOutput))
                {
                    var parts = nvidiaSmiOutput.Trim().Split(',');
                    if (parts.Length >= 2)
                    {
                        if (double.TryParse(parts[0].Trim(), out var tempValue))
                            temp = tempValue;
                        if (double.TryParse(parts[1].Trim(), out var usageValue))
                            usage = usageValue;
                    }
                }
            }
            
            // Fallback: Try Open Hardware Monitor WMI
            if (temp == 0 || usage == 0)
            {
                try
                {
                    using var ohmSearcher = new ManagementObjectSearcher(@"root\OpenHardwareMonitor", 
                        "SELECT * FROM Sensor WHERE SensorType='Temperature' AND Name LIKE '%GPU%'");
                    foreach (ManagementObject sensor in ohmSearcher.Get())
                    {
                        var value = sensor["Value"];
                        if (value != null && temp == 0)
                            temp = Math.Round(Convert.ToDouble(value), 1);
                    }

                    using var loadSearcher = new ManagementObjectSearcher(@"root\OpenHardwareMonitor", 
                        "SELECT * FROM Sensor WHERE SensorType='Load' AND Name LIKE '%GPU Core%'");
                    foreach (ManagementObject sensor in loadSearcher.Get())
                    {
                        var value = sensor["Value"];
                        if (value != null && usage == 0)
                            usage = Math.Round(Convert.ToDouble(value), 1);
                    }
                }
                catch { /* Open Hardware Monitor not installed */ }
            }

            return (temp, usage);
        }
        catch
        {
            return (0, 0);
        }
    }

    private void FindSystemPaths()
    {
        try
        {
            // On Windows, we use WMI for most hardware info, so we don't need to cache file paths
            // Find fan speed sources if available
            FindFanSpeedPaths();
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error finding system paths: {ex.Message}");
        }
    }

    private void FindFanSpeedPaths()
    {
        try
        {
            if (_fanPathsSearched)
                return;

            _fanPathsSearched = true;

            // On Windows, fan speeds are typically accessed through:
            // 1. Acer WMI ACPI methods
            // 2. Open Hardware Monitor WMI namespace
            // 3. Vendor-specific tools

            // Check if Open Hardware Monitor is available
            try
            {
                using var searcher = new ManagementObjectSearcher(@"root\OpenHardwareMonitor", 
                    "SELECT * FROM Sensor WHERE SensorType='Fan'");
                var fans = searcher.Get().Cast<ManagementObject>().ToList();
                if (fans.Any())
                {
                    _systemInfoPaths["fan_source"] = "OpenHardwareMonitor";
                    return;
                }
            }
            catch { /* Open Hardware Monitor not installed */ }

            // Check for nvidia-smi for GPU fan
            if (_gpuType == GpuType.Nvidia)
            {
                var nvidiaSmiOutput = RunCommand("nvidia-smi", "--query-gpu=fan.speed --format=csv,noheader");
                if (!string.IsNullOrWhiteSpace(nvidiaSmiOutput) && nvidiaSmiOutput.Contains("%"))
                {
                    _systemInfoPaths["gpu_fan_nvidia_smi"] = "true";
                }
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error finding fan speed paths: {ex.Message}");
            _fanPathsSearched = true;
        }
    }

    private (int cpuFan, int gpuFan) GetFanSpeeds()
    {
        try
        {
            // If paths haven't been searched yet, find them
            if (!_fanPathsSearched) FindFanSpeedPaths();

            var cpuFanSpeed = 0;
            var gpuFanSpeed = 0;

            // Try Open Hardware Monitor first
            if (_systemInfoPaths.ContainsKey("fan_source") && _systemInfoPaths["fan_source"] == "OpenHardwareMonitor")
            {
                try
                {
                    using var searcher = new ManagementObjectSearcher(@"root\OpenHardwareMonitor", 
                        "SELECT * FROM Sensor WHERE SensorType='Fan'");
                    var fanIndex = 0;
                    foreach (ManagementObject sensor in searcher.Get())
                    {
                        var value = sensor["Value"];
                        if (value != null)
                        {
                            var rpm = Convert.ToInt32(value);
                            if (fanIndex == 0)
                                cpuFanSpeed = rpm;
                            else if (fanIndex == 1)
                                gpuFanSpeed = rpm;
                            fanIndex++;
                        }
                    }
                }
                catch { /* Open Hardware Monitor query failed */ }
            }

            // Try nvidia-smi for GPU fan
            if (gpuFanSpeed == 0 && _systemInfoPaths.ContainsKey("gpu_fan_nvidia_smi"))
            {
                var nvidiaSmiOutput = RunCommand("nvidia-smi", "--query-gpu=fan.speed --format=csv,noheader");
                if (!string.IsNullOrWhiteSpace(nvidiaSmiOutput))
                {
                    var match = Regex.Match(nvidiaSmiOutput, @"(\d+)\s*%");
                    if (match.Success)
                    {
                        // Convert percentage to RPM (approximation: assume max 6000 RPM)
                        var percentage = int.Parse(match.Groups[1].Value);
                        gpuFanSpeed = percentage * 60; // Rough approximation
                    }
                }
            }

            CpuFanSpeedRPM = cpuFanSpeed;
            GpuFanSpeedRPM = gpuFanSpeed;
            return (cpuFanSpeed, gpuFanSpeed);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error in GetFanSpeeds: {ex.Message}");
            return (0, 0);
        }
    }

    private void InitializeFanAnimations(MaterialIcon cpuFanIcon, MaterialIcon gpuFanIcon)
    {
        // Set up render transforms
        cpuFanIcon.RenderTransform = new RotateTransform();
        gpuFanIcon.RenderTransform = new RotateTransform();

        // Create CPU fan animation
        _cpuFanAnimation = new Animation
        {
            Duration = TimeSpan.FromSeconds(1),
            IterationCount = IterationCount.Infinite,
            Children =
            {
                new KeyFrame
                {
                    Cue = new Cue(0d),
                    Setters = { new Setter(RotateTransform.AngleProperty, 0d) }
                },
                new KeyFrame
                {
                    Cue = new Cue(1d),
                    Setters = { new Setter(RotateTransform.AngleProperty, 360d) }
                }
            }
        };

        // Create GPU fan animation
        _gpuFanAnimation = new Animation
        {
            Duration = TimeSpan.FromSeconds(1),
            IterationCount = IterationCount.Infinite,
            Children =
            {
                new KeyFrame
                {
                    Cue = new Cue(0d),
                    Setters = { new Setter(RotateTransform.AngleProperty, 0d) }
                },
                new KeyFrame
                {
                    Cue = new Cue(1d),
                    Setters = { new Setter(RotateTransform.AngleProperty, 360d) }
                }
            }
        };

        // Start animations
        _cpuFanAnimation.RunAsync(cpuFanIcon);
        _gpuFanAnimation.RunAsync(gpuFanIcon);
    }

    private void UpdateFanAnimations()
    {
        try
        {
            var cpuFanIcon = this.FindControl<MaterialIcon>("CpuFanIcon");
            var gpuFanIcon = this.FindControl<MaterialIcon>("GpuFanIcon");

            if (cpuFanIcon == null || gpuFanIcon == null) return;

            if (!_animationsInitialized)
            {
                InitializeFanAnimations(cpuFanIcon, gpuFanIcon);
                _animationsInitialized = true;
            }

            if (Math.Abs(_cpuFanSpeedRpm - _lastCpuRpm) >= RPM_CHANGE_THRESHOLD)
                UpdateFanSpeed(_cpuFanAnimation, _cpuFanSpeedRpm, ref _lastCpuRpm);

            if (Math.Abs(_gpuFanSpeedRpm - _lastGpuRpm) > RPM_CHANGE_THRESHOLD)
                UpdateFanSpeed(_gpuFanAnimation, _gpuFanSpeedRpm, ref _lastGpuRpm);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error in UpdateFanAnimations: {ex.Message}");
        }
    }

    private void UpdateFanSpeed(Animation animation, int currentRpm, ref int lastRpm)
    {
        if (currentRpm < MIN_RPM_FOR_ANIMATION)
        {
            animation.Duration = TimeSpan.FromSeconds(MAX_ANIMATION_DURATION);
        }
        else
        {
            var durationSeconds = 1000.0 / currentRpm * 2;
            durationSeconds = Math.Max(MIN_ANIMATION_DURATION,
                Math.Min(MAX_ANIMATION_DURATION, durationSeconds));
            animation.Duration = TimeSpan.FromSeconds(durationSeconds);
        }

        lastRpm = currentRpm;
    }

    private (int percentage, string status, double timeRemaining) GetBatteryInfo()
    {
        if (!HasBattery) return (0, "No Battery", 0);

        try
        {
            var percentage = 0;
            var status = "Unknown";
            double timeRemaining = 0;

            using var searcher = new ManagementObjectSearcher("SELECT * FROM Win32_Battery");
            foreach (ManagementObject battery in searcher.Get())
            {
                // Get percentage
                var estimatedCharge = battery["EstimatedChargeRemaining"];
                if (estimatedCharge != null)
                    percentage = Convert.ToInt32(estimatedCharge);

                // Get status
                var batteryStatus = battery["BatteryStatus"];
                if (batteryStatus != null)
                {
                    var statusCode = Convert.ToInt32(batteryStatus);
                    status = statusCode switch
                    {
                        1 => "Discharging",
                        2 => "AC Power",
                        3 => "Fully Charged",
                        4 => "Low",
                        5 => "Critical",
                        6 => "Charging",
                        7 => "Charging (High)",
                        8 => "Charging (Low)",
                        9 => "Charging (Critical)",
                        10 => "Undefined",
                        11 => "Partially Charged",
                        _ => "Unknown"
                    };
                }

                // Get estimated runtime (in minutes)
                var runtime = battery["EstimatedRunTime"];
                if (runtime != null)
                {
                    var minutes = Convert.ToInt32(runtime);
                    if (minutes != 71582788) // Invalid/unknown value
                        timeRemaining = minutes / 60.0; // Convert to hours
                }
            }

            return (percentage, status, timeRemaining);
        }
        catch
        {
            return (0, "Error", 0);
        }
    }

    private string RunCommand(string command, string arguments)
    {
        try
        {
            using var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = command,
                    Arguments = arguments,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true
                }
            };

            process.Start();
            var output = process.StandardOutput.ReadToEnd();
            process.WaitForExit();
            return output;
        }
        catch
        {
            return string.Empty;
        }
    }

    protected bool SetProperty<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
        return true;
    }

    protected virtual void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }

    private class MetricsData
    {
        public double CpuUsage { get; set; }
        public double CpuTemp { get; set; }
        public double RamUsage { get; set; }
        public double GpuTemp { get; set; }
        public double GpuUsage { get; set; }
        public int BatteryPercentage { get; set; }
        public string BatteryStatus { get; set; } = "Unknown";
        public string BatteryTimeRemaining { get; set; } = "0";
        public int CpuFanSpeedRPM { get; set; }
        public int GpuFanSpeedRPM { get; set; }
    }

    private enum GpuType
    {
        Unknown,
        Nvidia,
        Amd,
        Intel
    }
}