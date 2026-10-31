using ScreenRecorderLib;
using System.Text.Json;
using RocketLeagueCaptureEngine;

// Binary fragmented MP4 is written to stdout; diagnostics go to stderr.
// The parent process owns retention, hotkeys, final MP4 and Drive uploads.
try
{
    if (args.Length == 1 && args[0] == "--list-devices")
    {
        var outputs = Recorder.GetSystemAudioLoopbackDevices().Select(d => d.FriendlyName).ToArray();
        var microphones = Recorder.GetSystemAudioCaptureDevices().Select(d => d.FriendlyName).ToArray();
        Console.WriteLine(JsonSerializer.Serialize(new { outputs, microphones }));
        return 0;
    }
    if (args.Length != 1) throw new ArgumentException("A configuration file is required");
    var settings = JsonSerializer.Deserialize<CaptureSettings>(File.ReadAllText(args[0]))
                   ?? throw new ArgumentException("Capture settings are empty");
    if (settings.Fps is not (30 or 60)) throw new ArgumentException("FPS must be 30 or 60");
    var display = settings.Monitor is null ? DisplayRecordingSource.MainMonitor : new DisplayRecordingSource(settings.Monitor);
    if (display is null) throw new InvalidOperationException("The requested display is unavailable");
    Console.Error.WriteLine("Capture display: " + display.DeviceName);
    display.RecorderApi = RecorderApi.WindowsGraphicsCapture;
    // Windows may ignore this preference unless the user has granted its
    // borderless-capture permission; no Windows privacy settings are changed.
    display.IsBorderRequired = false;
    var audio = new List<AudioSourceBase>();
    audio.Add(FindOutput(settings.AudioDevice));
    if (settings.Microphone is not null) audio.Add(FindMicrophone(settings.Microphone));
    var options = new RecorderOptions
    {
        SourceOptions = new SourceOptions { RecordingSources = { display } },
        AudioOptions = new AudioOptions { IsAudioEnabled = true, AudioSources = audio },
        VideoEncoderOptions = new VideoEncoderOptions
        {
            Framerate = settings.Fps, IsHardwareEncodingEnabled = settings.HardwareEncoding, IsFixedFramerate = settings.FixedFramerate,
            // The default buffered encoder can stop emitting fragments on a
            // static desktop. Low latency keeps the live replay stream flowing.
            IsLowLatencyEnabled = true,
            Bitrate = settings.Bitrate, IsFragmentedMp4Enabled = true,
            Encoder = new H264VideoEncoder { BitrateMode = H264BitrateControlMode.UnconstrainedVBR }
        }
    };
    if (settings.Width > 0 && settings.Height > 0)
        options.OutputOptions = new OutputOptions { OutputFrameSize = new ScreenSize(settings.Width, settings.Height) };
    using var stream = new FragmentOutputStream(Console.OpenStandardOutput());
    using var recorder = Recorder.CreateRecorder(options);
    using var finished = new ManualResetEventSlim(false);
    string? failure = null;
    int firstFrameReported = 0;
    long framesRecorded = 0;
    recorder.OnRecordingComplete += (_, _) => finished.Set();
    recorder.OnRecordingFailed += (_, e) => { failure = e.Error; finished.Set(); };
    recorder.OnStatusChanged += (_, e) => Console.Error.WriteLine("Capture status: " + e.Status);
    recorder.OnFrameRecorded += (_, e) =>
    {
        Interlocked.Increment(ref framesRecorded);
        if (Interlocked.Exchange(ref firstFrameReported, 1) == 0)
            Console.Error.WriteLine("CAPTURE_FIRST_FRAME_MS " + e.Timestamp);
    };
    recorder.Record(stream);
    var commands = Task.Run(() => { while (Console.ReadLine() is string line) { if (line == "stop") break; } });
    var progress = System.Diagnostics.Stopwatch.StartNew();
    while (!finished.IsSet && !commands.IsCompleted)
    {
        Thread.Sleep(100);
        if (progress.ElapsedMilliseconds >= 1000)
        {
            Console.Error.WriteLine($"CAPTURE_PROGRESS {Interlocked.Read(ref framesRecorded)} {stream.BytesWritten}");
            progress.Restart();
        }
    }
    if (!finished.IsSet) recorder.Stop();
    if (!finished.Wait(TimeSpan.FromSeconds(15))) throw new TimeoutException("Capture could not stop cleanly");
    if (failure is not null) throw new InvalidOperationException(failure);
    return 0;
}
catch (Exception ex)
{
    Console.Error.WriteLine("Capture failed: " + ex.Message);
    return 1;
}

static string Normalize(string value) => value.Replace(" [Loopback]", "", StringComparison.OrdinalIgnoreCase).Trim();
static AudioSourceBase FindOutput(string? name)
{
    if (name is null) return LoopbackAudioSource.Default ?? throw new InvalidOperationException("No default audio output");
    var devices = Recorder.GetSystemAudioLoopbackDevices().Where(d => string.Equals(Normalize(d.FriendlyName), Normalize(name), StringComparison.OrdinalIgnoreCase)).ToList();
    return devices.Count == 1 ? devices[0] : throw new InvalidOperationException("The selected output device was not found uniquely");
}
static AudioSourceBase FindMicrophone(string name)
{
    var devices = Recorder.GetSystemAudioCaptureDevices().Where(d => string.Equals(Normalize(d.FriendlyName), Normalize(name), StringComparison.OrdinalIgnoreCase)).ToList();
    return devices.Count == 1 ? devices[0] : throw new InvalidOperationException("The selected microphone was not found uniquely");
}

internal sealed record CaptureSettings
{
    public int Fps { get; init; } = 60;
    public int Bitrate { get; init; } = 20_000_000;
    public int Width { get; init; }
    public int Height { get; init; }
    public bool HardwareEncoding { get; init; } = true;
    public bool FixedFramerate { get; init; } = true;
    public string? Monitor { get; init; }
    public string? AudioDevice { get; init; }
    public string? Microphone { get; init; }
}
