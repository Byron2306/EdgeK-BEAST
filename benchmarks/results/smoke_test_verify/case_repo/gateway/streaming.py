async def collect_stream(chunks):
    out = []
    async for chunk in chunks:
        if not chunk:
            break
        out.append(chunk)
    return "".join(out)
