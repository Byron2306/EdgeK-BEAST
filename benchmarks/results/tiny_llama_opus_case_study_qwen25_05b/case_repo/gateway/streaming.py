async def collect_stream(chunks):
    out = []
    async for chunk in chunks:
        if chunk is None:
            break
        out.append(chunk)
    return "".join(out)
