def collect_stream(chunks):
    out = []
    for chunk in chunks:
        if chunk is None:
            break
        out.append(chunk)
    return out
