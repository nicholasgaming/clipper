using ScreenRecorderLib;
using System.Diagnostics;

// Standalone capture benchmark; never overwrite a previous clip.
if (args.Length != 2 || !int.TryParse(args[1], out var seconds) || seconds < 3 || seconds > 120)
{
    Console.Error.WriteLine("Usage: RocketLeagueCaptureProbe <new-output.mp4> <seconds>");
    return 2;
}
string output = Path.GetFullPath(args[0]);
if (File.Exists(output))
{
    Console.Error.WriteLine("Output already exists; refusing to overwrite it.");
    return 2;
}
Directory.CreateDirectory(Path.GetDirectoryName(output)!);
var display = DisplayRecordingSource.MainMonitor ?? throw new InvalidOperationException("No primary display was found");
display.RecorderApi = RecorderApi.WindowsGraphicsCapture;
var loopback = LoopbackAudioSource.Default ?? throw new InvalidOperationException("No default audio output was found");
var options = new RecorderOptions
{
    SourceOptions = new SourceOptions { RecordingSources = { display } },
    AudioOptions = new AudioOptions { IsAudioEnabled = true, AudioSources = new List<AudioSourceBase> { loopback } },
    VideoEncoderOptions = new VideoEncoderOptions
    {
        Framerate = 60, IsHardwareEncodingEnabled = true, IsFixedFramerate = true,
        Bitrate = 20_000_000, IsFragmentedMp4Enabled = true,
        Encoder = new H264VideoEncoder { BitrateMode = H264BitrateControlMode.UnconstrainedVBR }
    }
};
using var recorder = Recorder.CreateRecorder(options);
using var finished = new ManualResetEventSlim(false);
string? error = null;
recorder.OnRecordingComplete += (_, e) => { Console.WriteLine("Recording completed"); finished.Set(); };
recorder.OnRecordingFailed += (_, e) => { error = e.Error; finished.Set(); };
recorder.OnStatusChanged += (_, e) => Console.WriteLine("Status: " + e.Status);
var timer = Stopwatch.StartNew();
int reported = 0;
recorder.OnFrameRecorded += (_, e) =>
{
    if (Interlocked.Exchange(ref reported, 1) == 0)
        Console.WriteLine("FIRST " + e.Timestamp + " " + e.FrameNumber);
    if (e.FrameNumber % 120 == 0)
        Console.WriteLine("PROGRESS " + e.Timestamp + " " + e.FrameNumber);
};
TrackingStream? outputStream = null;
if (Environment.GetEnvironmentVariable("RLC_PROBE_DIRECT") == "1") recorder.Record(output);
else { outputStream = new TrackingStream(output); recorder.Record(outputStream); }
Thread.Sleep(TimeSpan.FromSeconds(seconds));
recorder.Stop();
if (!finished.Wait(TimeSpan.FromSeconds(30)))
{
    Console.Error.WriteLine("Timed out waiting for recording finalization");
    return 1;
}
if (error is not null)
{
    Console.Error.WriteLine("Recording failed: " + error);
    return 1;
}
Console.WriteLine($"Elapsed={timer.Elapsed.TotalSeconds:F1}s frames={recorder.CurrentFrameNumber}");
if (outputStream is not null) { Console.WriteLine(outputStream.Report()); outputStream.Dispose(); }
return 0;
