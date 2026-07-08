def collect_stream(chunks):
    out = []
    for chunk in chunks:
        if not chunk:
            break
        out.append(chunk)
    return out
