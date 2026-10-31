using System.Text;

// Diagnostic wrapper for investigating the Media Foundation fragmented MP4
// sink's seek/write behavior. No captured audio or video is logged.
internal sealed class TrackingStream : Stream
{
    private readonly FileStream file;
    private readonly List<string> unusual = new();
    private long writes, bytes, backwardsWrites, seeks, reads, setLengths;
    private long maxLength;

    public TrackingStream(string path) => file = new FileStream(path, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.Read);
    public override bool CanRead => true;
    public override bool CanSeek => true;
    public override bool CanWrite => true;
    public override long Length => file.Length;
    public override long Position { get => file.Position; set { seeks++; file.Position = value; } }
    public override void Flush() => file.Flush();
    public override int Read(byte[] buffer, int offset, int count) { reads++; return file.Read(buffer, offset, count); }
    public override long Seek(long offset, SeekOrigin origin) { seeks++; return file.Seek(offset, origin); }
    public override void SetLength(long value) { setLengths++; file.SetLength(value); }
    public override void Write(byte[] buffer, int offset, int count)
    {
        long at = file.Position;
        if (at < maxLength)
        {
            backwardsWrites++;
            if (unusual.Count < 30) unusual.Add($"offset={at}, length={count}, previousEnd={maxLength}");
        }
        file.Write(buffer, offset, count);
        maxLength = Math.Max(maxLength, file.Position);
        writes++;
        bytes += count;
    }
    public string Report() => $"writes={writes} bytes={bytes} backwardWrites={backwardsWrites} seeks={seeks} reads={reads} setLengths={setLengths}\n" + string.Join("\n", unusual);
    protected override void Dispose(bool disposing) { if (disposing) file.Dispose(); base.Dispose(disposing); }
}
