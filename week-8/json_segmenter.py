import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PCAP_SUFFIXES = {".pcap", ".pcapng"}


EXCLUDE_KEYWORDS = [
    "authbasic",
    "authorization_tree",
    "data_data_data",
    "data.data.data",
]


def read_text_auto_encoding(path: str) -> str:
    raw = Path(path).read_bytes()

    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")

    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp949", errors="replace")


def load_json_packets(path: str) -> List[Dict[str, Any]]:
    input_path = Path(path)

    if input_path.suffix.lower() in PCAP_SUFFIXES:
        raise ValueError(
            "json_segmenter.py expects JSON, not PCAP/PCAPNG. "
            "Convert first with tshark -T json or -T ek."
        )

    text = read_text_auto_encoding(path)
    stripped = text.strip()

    if not stripped:
        return []

    # tshark -T json
    try:
        obj = json.loads(stripped)

        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]

        if isinstance(obj, dict):
            if "packets" in obj and isinstance(obj["packets"], list):
                return [x for x in obj["packets"] if isinstance(x, dict)]
            return [obj]

    except json.JSONDecodeError:
        pass

    # tshark -T ek / NDJSON
    packets: List[Dict[str, Any]] = []

    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(item, dict):
            continue

        if "_source" in item or "layers" in item:
            packets.append(item)
        elif "timestamp" in item and "layers" in item:
            packets.append(item)

    return packets


def get_layers(packet: Dict[str, Any]) -> Dict[str, Any]:
    if "_source" in packet:
        return packet.get("_source", {}).get("layers", {}) or {}

    return packet.get("layers", {}) or {}


def first_value(value: Any) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, list):
        if not value:
            return None
        return first_value(value[0])

    if isinstance(value, dict):
        return None

    return str(value)


def candidate_keys(name: str) -> List[str]:
    """
    tshark -T json / -T ek의 field naming 차이를 흡수한다.

    예:
    frame.number
    frame_number
    frame_frame_number
    """
    out = [name]

    dot_to_under = name.replace(".", "_")
    out.append(dot_to_under)

    parts = name.split(".", 1)
    if len(parts) == 2:
        prefix, _ = parts
        out.append(f"{prefix}_{dot_to_under}")

    return list(dict.fromkeys(out))


def get_field(layer: Dict[str, Any], *names: str) -> Optional[str]:
    """
    layer 안에서 field를 robust하게 찾는다.
    """
    if not isinstance(layer, dict):
        return None

    for name in names:
        for key in candidate_keys(name):
            if key in layer:
                value = first_value(layer.get(key))
                if value is not None:
                    return value

    # 마지막 fallback: normalize 비교
    normalized_map = {
        str(k).replace(".", "_").lower(): k
        for k in layer.keys()
    }

    for name in names:
        for key in candidate_keys(name):
            nk = key.replace(".", "_").lower()
            real_key = normalized_map.get(nk)
            if real_key is not None:
                value = first_value(layer.get(real_key))
                if value is not None:
                    return value

    return None


def flatten_strings(obj: Any, prefix: str = "") -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            next_prefix = f"{prefix}.{k}" if prefix else str(k)
            out.extend(flatten_strings(v, next_prefix))

    elif isinstance(obj, list):
        for idx, v in enumerate(obj):
            out.extend(flatten_strings(v, f"{prefix}[{idx}]"))

    else:
        if obj is not None:
            value = str(obj)
            if value:
                out.append((prefix, value))

    return out


def should_exclude_field(key: str, value: str) -> bool:
    lowered_key = key.lower()
    lowered_value = value.lower()

    if any(ex in lowered_key for ex in EXCLUDE_KEYWORDS):
        return True

    # Wireshark가 이미 Basic Auth를 디코딩한 결과는 제외
    if "authbasic" in lowered_key:
        return True

    # Java class / raw binary hex blob은 encoding_decode_tool 입력에서 제외
    if looks_like_large_hex_blob(value):
        return True

    # True/False 같은 control flag는 제외
    if lowered_value in {"true", "false"}:
        return True

    return False


def looks_like_large_hex_blob(value: str) -> bool:
    """
    ca:fe:ba:be:... 같은 긴 바이너리 hex blob 제외.
    """
    if len(value) < 120:
        return False

    colon_count = value.count(":")
    if colon_count < 20:
        return False

    hex_chars = set("0123456789abcdefABCDEF:")
    ratio = sum(ch in hex_chars for ch in value) / max(len(value), 1)

    return ratio > 0.9


def get_frame_info(layers: Dict[str, Any]) -> Dict[str, Any]:
    frame = layers.get("frame", {}) or {}

    no = get_field(frame, "frame.number")
    time_rel = get_field(frame, "frame.time_relative")
    time_utc = get_field(frame, "frame.time_utc")

    return {
        "no": int(no) if no and no.isdigit() else None,
        "time": float(time_rel) if time_rel else None,
        "timestamp_utc": time_utc,
    }


def build_stream_key(layers: Dict[str, Any]) -> str:
    ip = layers.get("ip", {}) or {}
    tcp = layers.get("tcp", {}) or {}
    udp = layers.get("udp", {}) or {}

    src_ip = get_field(ip, "ip.src")
    dst_ip = get_field(ip, "ip.dst")

    if tcp:
        src_port = get_field(tcp, "tcp.srcport")
        dst_port = get_field(tcp, "tcp.dstport")
        proto = "tcp"
    elif udp:
        src_port = get_field(udp, "udp.srcport")
        dst_port = get_field(udp, "udp.dstport")
        proto = "udp"
    else:
        src_port = None
        dst_port = None
        proto = "unknown"

    src_ip = src_ip or "unknown_src"
    dst_ip = dst_ip or "unknown_dst"
    src_port = src_port or "0"
    dst_port = dst_port or "0"

    return f"{src_ip}:{src_port}-{dst_ip}:{dst_port}-{proto}"


def detect_protocol(layers: Dict[str, Any]) -> str:
    frame = layers.get("frame", {}) or {}
    protocols = get_field(frame, "frame.protocols") or ""
    p = protocols.lower()

    if "http" in p:
        return "HTTP"
    if "ldap" in p:
        return "LDAP"
    if "tls" in p or "ssl" in p:
        return "TLS"
    if "dns" in p:
        return "DNS"
    if "tcp" in p:
        return "TCP"
    if "udp" in p:
        return "UDP"

    return "UNKNOWN"


def is_encrypted(layers: Dict[str, Any]) -> bool:
    frame = layers.get("frame", {}) or {}
    protocols = get_field(frame, "frame.protocols") or ""
    p = protocols.lower()

    if "tls" in p or "ssl" in p:
        return True

    tcp = layers.get("tcp", {}) or {}
    src_port = get_field(tcp, "tcp.srcport")
    dst_port = get_field(tcp, "tcp.dstport")

    if (src_port in {"443", "636"} or dst_port in {"443", "636"}) and "http" not in p:
        return True

    return False


def hex_payload_to_text(hex_payload: str) -> Optional[str]:
    try:
        cleaned = hex_payload.replace(":", "").replace(" ", "").strip()
        raw = bytes.fromhex(cleaned)
    except Exception:
        return None

    text = raw.decode("utf-8", errors="replace")

    printable = sum(ch.isprintable() or ch in "\r\n\t" for ch in text)
    ratio = printable / max(len(text), 1)

    if ratio < 0.75:
        return None

    return text


def extract_http_segments(layers: Dict[str, Any]) -> List[Dict[str, str]]:
    http = layers.get("http", {}) or {}
    segments: List[Dict[str, str]] = []

    if not isinstance(http, dict):
        return segments

    # 1. 핵심 HTTP 원본 필드
    key_map = [
        ("http.request.uri", "http_request.uri"),
        ("http.request.full_uri", "http_request.full_uri"),
        ("http.host", "http_header.host"),
        ("http.user_agent", "http_header.user_agent"),
        ("http.authorization", "http_header.authorization"),
    ]

    for key, position in key_map:
        value = get_field(http, key)
        if value and not should_exclude_field(key, value):
            segments.append({"position": position, "payload": value})

    # 2. request/response line 계열만 추가로 추출
    for key, value in flatten_strings(http):
        if not value:
            continue

        lowered = key.lower()

        if should_exclude_field(key, value):
            continue

        # 너무 넓게 다 긁지 말고, 실제 요청/헤더/URI 관련 필드만 허용
        allowed = any(token in lowered for token in [
            "request_line",
            "response_line",
            "request.uri",
            "request_uri",
            "full_uri",
            "host",
            "user_agent",
            "authorization",
            "text",
        ])

        if not allowed:
            continue

        if "authorization" in lowered:
            position = "http_header.authorization"
        elif "user_agent" in lowered:
            position = "http_header.user_agent"
        elif "request_uri" in lowered or "request.uri" in lowered:
            position = "http_request.uri"
        elif "full_uri" in lowered:
            position = "http_request.full_uri"
        elif "request_line" in lowered:
            position = "http_header.request_line"
        elif "response_line" in lowered:
            position = "http_header.response_line"
        elif "host" in lowered:
            position = "http_header.host"
        else:
            position = f"http_field.{key}"

        segments.append({"position": position, "payload": value})

    return segments


def extract_dns_segments(layers: Dict[str, Any]) -> List[Dict[str, str]]:
    dns = layers.get("dns", {}) or {}
    segments: List[Dict[str, str]] = []

    if not isinstance(dns, dict):
        return segments

    for key, value in flatten_strings(dns):
        lowered = key.lower()
        if "qry.name" in lowered or "qry_name" in lowered:
            segments.append({"position": "dns_query.name", "payload": value})
        elif "resp.name" in lowered or "resp_name" in lowered:
            segments.append({"position": "dns_response.name", "payload": value})

    return segments


def extract_tcp_text_segment(layers: Dict[str, Any]) -> Optional[Dict[str, str]]:
    tcp = layers.get("tcp", {}) or {}
    hex_payload = get_field(tcp, "tcp.payload")

    if not hex_payload:
        return None

    text = hex_payload_to_text(hex_payload)
    if not text:
        return None

    if looks_like_large_hex_blob(text):
        return None

    return {
        "position": "tcp_payload.text",
        "payload": text,
    }


def packet_to_segments(packet: Dict[str, Any]) -> List[Dict[str, Any]]:
    layers = get_layers(packet)
    if not layers:
        return []

    frame_info = get_frame_info(layers)
    stream_key = build_stream_key(layers)
    protocol = detect_protocol(layers)
    encrypted = is_encrypted(layers)

    # 암호화된 TLS/LDAPS 내부 payload는 추출하지 않음
    if encrypted and protocol == "TLS":
        return [{
            **frame_info,
            "stream_key": stream_key,
            "protocol": protocol,
            "encrypted": True,
            "position": "encrypted_tls_stream",
            "payload": "",
            "notes": "encrypted stream; payload not extracted by json_segmenter",
        }]

    extracted: List[Dict[str, str]] = []
    extracted.extend(extract_http_segments(layers))
    extracted.extend(extract_dns_segments(layers))

    tcp_text = extract_tcp_text_segment(layers)
    if tcp_text:
        extracted.append(tcp_text)

    out: List[Dict[str, Any]] = []
    seen = set()

    for item in extracted:
        payload = item.get("payload")
        position = item.get("position")

        if not payload:
            continue

        dedup_key = (frame_info.get("no"), position, payload)
        if dedup_key in seen:
            continue

        seen.add(dedup_key)

        out.append({
            **frame_info,
            "stream_key": stream_key,
            "protocol": protocol,
            "encrypted": encrypted,
            "position": position,
            "payload": payload,
        })

    return out


def group_by_stream(flat_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    streams: Dict[str, Dict[str, Any]] = {}

    for seg0 in flat_segments:
        seg = dict(seg0)

        stream_key = seg.pop("stream_key")
        protocol = seg.pop("protocol")
        encrypted = seg.pop("encrypted")

        if stream_key not in streams:
            streams[stream_key] = {
                "stream_key": stream_key,
                "protocol": protocol,
                "encrypted": encrypted,
                "segments": [],
            }

        streams[stream_key]["segments"].append(seg)

    return {"streams": list(streams.values())}


def build_default_output_path(input_path: str) -> str:
    path = Path(input_path)
    parts = list(path.parts)

    if "raw" in parts:
        idx = parts.index("raw")
        parts[idx] = "segmented"
        output_dir = Path(*parts[:-1])
    else:
        output_dir = path.parent

    output_dir.mkdir(parents=True, exist_ok=True)
    return str(output_dir / f"{path.stem}_segments.json")


def segment_json(input_path: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    packets = load_json_packets(input_path)

    flat_segments: List[Dict[str, Any]] = []
    packets_with_layers = 0
    packets_with_segments = 0

    for packet in packets:
        layers = get_layers(packet)

        if layers:
            packets_with_layers += 1

        segs = packet_to_segments(packet)

        if segs:
            packets_with_segments += 1

        flat_segments.extend(segs)

    result = group_by_stream(flat_segments)
    final_output = output_path or build_default_output_path(input_path)

    with open(final_output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "input": input_path,
        "output": final_output,
        "packet_count": len(packets),
        "packets_with_layers": packets_with_layers,
        "packets_with_segments": packets_with_segments,
        "stream_count": len(result["streams"]),
        "segment_count": sum(len(s["segments"]) for s in result["streams"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=False)
    args = parser.parse_args()

    try:
        result = segment_json(args.input, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({
            "ok": False,
            "error": {
                "code": "JSON_SEGMENTER_ERROR",
                "message": str(e),
            }
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()