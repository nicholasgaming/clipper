namespace RocketLeagueCaptureEngine;

// The Media Foundation fragmented-MP4 sink writes append-only during capture,
// then seeks back to update the MP4 header on finalization. A live fragmented
// MP4 header is already decodable, so the final header rewrite is omitted from
// the pipe. Unexpected seeks fail rather than silently corrupting output.
internal sealed class FragmentOutputStream : Stream
{
    private readonly Stream destination;
    private long position;
    private long length;
    private long bytesWritten;
    public long BytesWritten => Interlocked.Read(ref bytesWritten);
    private readonly object gate = new();

    public FragmentOutputStream(Stream destination) => this.destination = destination;
    public override bool CanRead => true;
    public override bool CanSeek => true;
    public override bool CanWrite => true;
    public override long Length { get { lock (gate) return length; } }
    public override long Position
    {
        get { lock (gate) return position; }
        set { lock (gate) { if (value < 0) throw new IOException("Negative stream position"); position = value; } }
    }
    public override void Flush() { lock (gate) destination.Flush(); }
    public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException("Capture output is write-only");
    public override long Seek(long offset, SeekOrigin origin)
    {
        lock (gate)
        {
            long next = origin switch { SeekOrigin.Begin => offset, SeekOrigin.Current => position + offset,
                                        SeekOrigin.End => length + offset, _ => throw new ArgumentOutOfRangeException(nameof(origin)) };
            if (next < 0) throw new IOException("Negative stream position");
            position = next;
            return next;
        }
    }
    public override void SetLength(long value)
    {
        lock (gate) { if (value != length) throw new IOException("Unexpected output resize"); }
    }
    public override void Write(byte[] buffer, int offset, int count)
    {
        lock (gate)
        {
            if (position == length)
            {
                destination.Write(buffer, offset, count);
                Interlocked.Add(ref bytesWritten, count);
                position += count;
                length += count;
            }
            else if (position < 4096 && position + count <= Math.Min(length, 4096))
            {
                // Ignore only a bounded rewrite to the already-sent header.
                position += count;
            }
            else throw new IOException("Unexpected non-header seek in capture output");
        }
    }
}
