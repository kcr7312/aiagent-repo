좋아. 아래는 `TASK.md` 템플릿의 9개 섹션에 맞춘 **축소판 제출용 `design.md`**야. 이번 버전은 네가 정리한 대로 **초기 구현 단계**에 집중했고, Tool은 5개, Step은 6단계 이내, TLS/SSL 암호화 패킷은 헤더/페이로드 기준으로 제외하도록 반영했어. 템플릿 요구사항도 “9개 섹션 순서대로 작성”이고 Tool은 2~5개 권장이라 이 구성이 맞음. ([GitHub][1])

````md
# 6주차 AI Agent 설계서

## 1. 개요·목적

본 설계서는 포렌식용 PCAP/PCAPNG 파일에서 평문 또는 부분 평문 payload를 포함한 스트림을 선별하고, 해당 payload 안에 포함된 인코딩·난독화 후보를 자동 디코딩하는 **Forensic Payload Decoding Strategy Agent**를 제안한다.

타깃 사용자는 보안 관제 분석가 또는 침해사고 분석가이다. 기존에는 Wireshark의 Follow Stream 기능으로 세션 payload를 직접 확인하고, Base64, Hex, URL Decode, gzip, XOR 등을 수동으로 반복 시도해야 했다. 본 Agent는 이 반복 작업을 자동화하되, 자동 디코딩이 실패하거나 모호한 경우 AI가 실패 원인을 해석하고 다음 디코딩 전략을 선택하는 것을 목적으로 한다.

본 문제는 단일 LLM 호출이나 RAG만으로 해결할 수 없다. 분석 대상은 문서가 아니라 PCAP에서 추출된 payload이며, 요청과 중간 결과에 따라 Tool 호출 경로가 달라진다. 예를 들어 TLS/SSL 헤더가 확인되면 암호화 세션으로 제외하고, HTTP body에서 Base64 후보가 확인되면 디코딩을 시도한다. 반면 DNS label에 조각난 인코딩 후보가 발견되면 주변 segment 수집 또는 재조합 전략이 필요하다.

따라서 본 Agent는 고정된 순서의 Workflow가 아니라, payload 상태와 디코딩 결과에 따라 Tool 조합을 달리 선택하는 Agent이다.

---

## 2. 사용자 시나리오

### Persona

- 이름: 김분석
- 역할: 보안 관제 / 침해사고 분석 담당자
- 목적: 포렌식용 PCAP에서 인코딩·난독화된 payload 후보를 빠르게 확인하고, 자동 디코딩이 실패한 경우 다음 분석 방향을 알고 싶다.

---

### 대표 요청 1

```text
이 PCAP에서 디코딩 가능한 payload 후보만 찾아줘.
````

단일 Tool 한 번으로 끝나지 않는 이유:

* PCAP 메타 추출이 필요하고,
* 암호화 세션은 제외해야 하며,
* 선택된 스트림에서 payload를 추출한 뒤,
* 인코딩 후보 탐지와 자동 디코딩을 수행해야 한다.

예상 Tool 경로:

```text
pcap_preprocess_tool
→ stream_filter_tool
→ payload_extract_tool
→ encoding_decode_tool
```

---

### 대표 요청 2

```text
TLS나 SSL처럼 암호화된 세션은 빼고, 평문 payload에서만 인코딩 후보를 찾아줘.
```

단일 Tool 한 번으로 끝나지 않는 이유:

* 포트 번호만으로는 암호화 여부를 판단할 수 없고,
* 헤더와 payload 특성을 기준으로 제외해야 하며,
* 제외되지 않은 스트림에 대해서만 payload 분석을 수행해야 한다.

예상 Tool 경로:

```text
pcap_preprocess_tool
→ stream_filter_tool
→ payload_extract_tool
→ encoding_decode_tool
```

단, TLS/SSL로 식별된 스트림은 `payload_extract_tool` 이후 단계로 넘어가지 않는다.

---

### 대표 요청 3

```text
자동 디코딩에 실패한 payload가 있으면 왜 실패했는지 보고 다음 시도 방법을 알려줘.
```

단일 Tool 한 번으로 끝나지 않는 이유:

* 자동 디코딩 실패 결과를 해석해야 하고,
* padding 오류, 조각난 payload, 다단계 인코딩 가능성 등을 구분해야 하며,
* 실패 유형에 따라 padding 보정, 주변 segment 수집, 분석 종료 중 다음 전략이 달라진다.

예상 Tool 경로:

```text
pcap_preprocess_tool
→ stream_filter_tool
→ payload_extract_tool
→ encoding_decode_tool
→ decode_strategy_tool
```

---

## 3. 기능 요구사항

### Must-have

1. **PCAP 최소 메타 추출**

   * 입력: PCAP/PCAPNG 파일 경로
   * 출력: `No`, `Time`, `Timestamp`, `src_ip`, `dst_ip`, `src_port`, `dst_port`, `protocol`, `length`, `info`

2. **암호화 세션 제외**

   * 입력: 패킷 메타와 payload header 샘플
   * 출력: 분석 대상 스트림과 제외 스트림 목록
   * TLS/SSL/SSH 등 암호화 payload는 디코딩 대상에서 제외한다.

3. **Payload 추출**

   * 입력: 분석 대상으로 선별된 stream key
   * 출력: 해당 스트림의 payload segment 목록

4. **인코딩 후보 탐지 및 자동 디코딩**

   * 입력: payload segment
   * 출력: Base64, Base32, Hex, URL encoding, gzip/zlib, single-byte XOR 후보와 디코딩 결과

5. **디코딩 실패 전략 판단**

   * 입력: 자동 디코딩 실패 결과
   * 출력: 실패 유형과 다음 행동
   * 예: padding 보정, 주변 segment 수집, 다단계 디코딩 의심, 추가 분석 불필요

---

### Nice-to-have

1. **다단계 디코딩 후보 제안**

   * URL decode 이후 Base64 후보가 보이면 다음 단계 디코딩을 제안한다.

2. **DNS label 조각 후보 처리**

   * DNS query label에 순번 형태의 조각이 보이면 주변 segment 수집을 제안한다.

3. **디코딩 결과 우선순위 조정**

   * `cmd=`, `token=`, `path=`, `user=` 등 의미 있는 key-value 구조가 보이면 우선순위를 높인다.

---

## 4. Agent 패턴 선택과 근거

### 선택한 패턴

**ReAct 기반 Agent**

---

### 선택 근거

본 Agent는 전체 흐름이 복잡한 장기 계획 문제라기보다, Tool 실행 결과를 보고 다음 행동을 결정하는 문제에 가깝다. 특히 자동 디코딩 결과가 성공인지 실패인지, 실패했다면 어떤 실패 유형인지에 따라 다음 Tool 호출 여부가 달라진다.

따라서 `Thought → Action → Observation → Next Action` 형태의 ReAct 패턴이 적합하다. 초기 메타 추출과 payload 추출은 비교적 고정적이지만, 암호화 세션 제외, 디코딩 실패, 모호한 결과 처리에서는 중간 결과 기반 분기가 필요하다.

---

### 루프 구조도

```text
1. 사용자 요청 수신
2. pcap_preprocess_tool로 최소 메타 추출
3. stream_filter_tool로 암호화 세션 제외 및 분석 대상 선별
4. payload_extract_tool로 payload segment 추출
5. encoding_decode_tool로 인코딩 후보 탐지 및 자동 디코딩
6. 실패 또는 모호한 결과가 있을 때만 decode_strategy_tool 호출
7. 결과 요약 후 종료
```

---

## 5. 동작 명세

### 입력 스키마

```json
{
  "user_query": "TLS/SSL 세션은 빼고 디코딩 가능한 payload 후보만 찾아줘.",
  "pcap_path": "data/sample_forensic.pcapng",
  "options": {
    "exclude_encrypted": true,
    "max_streams": 20,
    "max_steps": 6
  }
}
```

필수 입력:

```text
- user_query
- pcap_path
```

선택 입력:

```text
- src_ip
- dst_ip
- protocol
- time_range
- max_streams
- exclude_encrypted
```

---

### 출력 스키마

```json
{
  "summary": "총 5개 스트림 중 1개는 TLS header가 확인되어 제외되었고, 2개 스트림에서 디코딩 가능한 payload 후보가 확인되었습니다.",
  "decoded_candidates": [
    {
      "stream_key": "192.168.10.8:50120-203.0.113.10:80-tcp",
      "candidate_type": "base64",
      "decode_status": "success",
      "decoded_preview": "user=admin&cmd=whoami",
      "score": 0.96
    }
  ],
  "failed_candidates": [
    {
      "stream_key": "192.168.10.5:53000-8.8.8.8:53-udp",
      "candidate_type": "base64_fragment",
      "decode_status": "failed",
      "failure_type": "partial_chunk",
      "recommended_action": "collect_neighbor_segments_and_retry"
    }
  ],
  "excluded_streams": [
    {
      "stream_key": "192.168.10.10:50121-203.0.113.30:443-tcp",
      "status": "excluded",
      "reason": "encrypted_payload",
      "evidence": [
        "TLS record header detected",
        "ClientHello pattern found"
      ]
    }
  ],
  "tool_trace": [
    "pcap_preprocess_tool",
    "stream_filter_tool",
    "payload_extract_tool",
    "encoding_decode_tool",
    "decode_strategy_tool"
  ]
}
```

---

### 정상 흐름 예시

시나리오: 사용자가 암호화 세션은 제외하고 디코딩 가능한 payload 후보만 찾아달라고 요청한 경우

```text
Step 1. Thought
사용자는 TLS/SSL 세션을 제외하고 평문 payload에서 인코딩 후보를 찾고 싶어 한다. 먼저 PCAP의 최소 메타를 추출해야 한다.

Step 2. Action
pcap_preprocess_tool 호출

Step 3. Observation
패킷 No, Time, Timestamp, IP, Port, Protocol, Length가 추출되었다. 일부 TCP 443 스트림에서 TLS ClientHello 패턴이 확인된다.

Step 4. Thought
포트 번호가 아니라 헤더와 payload 특징을 기준으로 암호화 세션을 제외해야 한다.

Step 5. Action
stream_filter_tool 호출

Step 6. Observation
1개 스트림은 TLS record header로 인해 제외되었다. 2개 스트림은 HTTP/DNS payload 후보로 선택되었다.

Step 7. Thought
선택된 스트림에서 payload segment를 추출한다.

Step 8. Action
payload_extract_tool 호출

Step 9. Observation
HTTP body에서 Base64-like 문자열이 확인되고, DNS label에서는 조각난 Base64-like 문자열이 확인된다.

Step 10. Thought
인코딩 후보를 자동 디코딩한다.

Step 11. Action
encoding_decode_tool 호출

Step 12. Observation
HTTP body의 Base64 후보는 성공적으로 디코딩되었다. DNS label 후보는 partial chunk 오류로 실패했다.

Step 13. Thought
실패한 DNS label 후보는 주변 segment 수집이 필요한지 판단해야 한다.

Step 14. Action
decode_strategy_tool 호출

Step 15. Observation
실패 유형은 partial_chunk이며, 주변 segment 수집 후 재시도를 권장한다.

Step 16. Final
성공 후보, 실패 후보, 암호화 제외 스트림을 요약하고 종료한다.
```

※ 실제 구현 제한은 6개 주요 처리 단계이며, 위 trace는 Thought/Action/Observation 단위로 세분화한 예시이다.

---

### 6개 주요 처리 Step

```text
Step 1. PCAP 최소 메타 추출
Step 2. 암호화 세션 제외 및 분석 대상 스트림 선별
Step 3. 선택 스트림의 payload 추출
Step 4. 인코딩 후보 탐지 및 자동 디코딩
Step 5. 실패/모호 케이스에 한해 AI 전략 판단
Step 6. 결과 요약 및 종료
```

---

### 암호화 세션 제외 기준

본 Agent는 TLS/SSL/SSH/VPN 등 암호화 payload를 복호화하지 않는다. 암호화 세션은 분석 실패가 아니라 **분석 범위 제외**로 처리한다.

#### 헤더 기반 제외 기준

다음 조건 중 하나 이상을 만족하면 암호화 세션 후보로 분류한다.

```text
- tshark 또는 Zeek에서 프로토콜이 TLS, SSL, SSH로 식별된 경우
- TCP payload 시작 부분에 TLS record header가 확인되는 경우
  - 0x16 0x03 0x01
  - 0x16 0x03 0x03
  - 0x17 0x03 0x03
- ClientHello 또는 ServerHello 구조가 확인되는 경우
- SSH banner가 확인되는 경우
  - SSH-2.0
```

#### Payload 기반 제외 기준

```text
- payload 대부분이 high entropy binary이고 printable string 비율이 낮은 경우
- TLS record 구조가 반복적으로 나타나는 경우
- HTTP, DNS, URI, key=value, printable string 등 인코딩 후보로 볼 수 있는 구조가 거의 없는 경우
- 디코딩 후보 문자열 추출 결과가 없고, payload가 암호화된 binary stream으로만 확인되는 경우
```

중요한 점:

```text
port 443이라는 이유만으로 제외하지 않는다.
암호화 여부는 포트 번호가 아니라 실제 payload header와 프로토콜 식별 결과를 기준으로 판단한다.
```

---

### 예외 흐름

#### 1. PCAP 파일을 읽을 수 없는 경우

```json
{
  "error": "pcap_read_error",
  "detail": "파일이 손상되었거나 지원하지 않는 형식입니다."
}
```

동작:

```text
- pcap_preprocess_tool 실패 사유를 출력한다.
- 이후 Tool은 호출하지 않는다.
- 분석을 종료한다.
```

---

#### 2. 모든 스트림이 암호화 세션으로 제외된 경우

```json
{
  "status": "no_decodable_stream",
  "detail": "분석 가능한 평문 또는 부분 평문 payload 스트림이 없습니다.",
  "excluded_reason": "encrypted_payload"
}
```

동작:

```text
- payload_extract_tool과 encoding_decode_tool을 호출하지 않는다.
- 제외된 스트림 목록과 제외 근거를 요약한다.
- 분석을 종료한다.
```

---

#### 3. Payload가 추출되지 않는 경우

```json
{
  "error": "payload_not_found",
  "detail": "선택된 스트림에서 분석 가능한 payload segment가 없습니다."
}
```

동작:

```text
- 해당 스트림은 디코딩 대상에서 제외한다.
- 다른 selected stream이 있으면 계속 진행한다.
- 없으면 종료한다.
```

---

#### 4. 디코딩 후보가 없는 경우

```json
{
  "status": "no_encoding_candidate",
  "detail": "payload 내에서 인코딩 후보 문자열이 확인되지 않았습니다."
}
```

동작:

```text
- decode_strategy_tool을 호출하지 않는다.
- 후보 없음으로 결과를 요약한다.
```

---

#### 5. 디코딩 실패 또는 모호한 경우

```json
{
  "decode_status": "failed",
  "failure_type": "partial_or_padding_error"
}
```

동작:

```text
- decode_strategy_tool을 호출한다.
- AI는 padding 보정, 주변 segment 수집, 다단계 디코딩 의심, 추가 분석 불필요 중 하나를 선택한다.
```

---

### 종료 조건

Agent는 다음 중 하나를 만족하면 종료한다.

```text
1. 6개 주요 Step이 완료된 경우
2. PCAP을 읽을 수 없는 경우
3. 분석 가능한 스트림이 없는 경우
4. 모든 selected stream에 대해 인코딩 후보 탐지와 자동 디코딩이 완료된 경우
5. 실패 후보에 대해 decode_strategy_tool의 다음 전략이 산출된 경우
6. 동일 후보에 대해 추가 재시도 없이 “초기 구현 범위 초과”로 판단한 경우
```

---

## 6. Tool 명세

| Tool 이름                | 목적                                 | 입력 스키마                                                             | 출력 스키마                                                                                                                                                                                          | 실패 시 반환                                                 | 사용 조건                                                 |
| ---------------------- | ---------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------------- |
| `pcap_preprocess_tool` | PCAP에서 Wireshark식 최소 메타를 추출한다.     | `{ "pcap_path": "string" }`                                        | `{ "packets": [{"no": int, "time": float, "timestamp": string, "src_ip": string, "dst_ip": string, "src_port": int, "dst_port": int, "protocol": "string", "length": int, "info": "string"}] }` | `{ "error": "pcap_read_error", "detail": "..." }`       | 모든 요청의 첫 단계에서 사용한다.                                   |
| `stream_filter_tool`   | 분석 대상 스트림을 선별하고 암호화 세션을 제외한다.      | `{ "packets": [], "exclude_encrypted": true, "max_streams": int }` | `{ "selected_streams": [], "excluded_streams": [] }`                                                                                                                                            | `{ "error": "stream_filter_failed", "detail": "..." }`  | 최소 메타 생성 후 사용한다. TLS/SSL/SSH 헤더가 있으면 제외한다.            |
| `payload_extract_tool` | 선택된 스트림에서 payload segment를 추출한다.   | `{ "pcap_path": "string", "stream_key": "string" }`                | `{ "stream_key": "string", "segments": [{"no": int, "time": float, "payload": "string", "position": "string"}] }`                                                                               | `{ "error": "payload_not_found", "detail": "..." }`     | `selected_streams`에 대해서만 사용한다. 암호화 제외 스트림에는 사용하지 않는다. |
| `encoding_decode_tool` | payload에서 인코딩 후보를 찾고 자동 디코딩을 시도한다. | `{ "stream_key": "string", "segments": [] }`                       | `{ "candidates": [], "failed_candidates": [] }`                                                                                                                                                 | `{ "error": "no_encoding_candidate", "detail": "..." }` | payload segment가 있을 때 사용한다.                           |
| `decode_strategy_tool` | 자동 디코딩 실패 또는 모호 케이스에서 다음 전략을 제안한다. | `{ "failed_candidate": {}, "context": {} }`                        | `{ "failure_type": "string", "recommended_action": "string", "reason": "string" }`                                                                                                              | `{ "error": "strategy_not_found", "detail": "..." }`    | `encoding_decode_tool`이 실패 후보를 반환한 경우에만 사용한다.         |

---

## 7. 데이터셋

본 과제는 실제 PCAP을 제출하지 않고, Mock 데이터셋을 사용한다. 단, 스키마는 tshark/Wireshark 방식으로 확장 가능한 형태로 구성한다.

### 데이터 출처

```text
data/sample_packets.csv
data/sample_stream_segments.json
data/sample_decode_results.json
```

데이터 특성:

```text
- 데이터 유형: CSV / JSON
- 업데이트 주기: 과제용 고정 Mock 데이터
- 인증 필요 여부: 없음
- 목적: PCAP 최소 메타 추출, 암호화 세션 제외, payload 추출, 인코딩 후보 디코딩 시뮬레이션
```

---

### sample_packets.csv

```csv
no,time,timestamp,src_ip,dst_ip,src_port,dst_port,protocol,length,info
1,0.000000,2026-05-01T10:00:01.123456,192.168.10.5,8.8.8.8,53000,53,DNS,120,Standard query 001.dXNlcj1hZG.example.com
2,0.015230,2026-05-01T10:00:01.138686,192.168.10.5,8.8.8.8,53000,53,DNS,118,Standard query 002.1pbiZjbWQ9.example.com
3,1.204822,2026-05-01T10:00:02.328278,192.168.10.8,203.0.113.10,50120,80,HTTP,512,POST /submit data=dXNlcj1hZG1pbiZjbWQ9d2hvYW1p
4,2.100400,2026-05-01T10:00:03.223856,192.168.10.9,198.51.100.20,50400,8080,TCP,256,Payload contains 68656c6c6f
5,3.500100,2026-05-01T10:00:04.623556,192.168.10.10,203.0.113.30,50121,443,TLS,1514,TLS ClientHello 16 03 03
```

예상 처리:

```text
- No. 1~2: DNS label에 조각난 Base64-like payload 후보
- No. 3: HTTP body 내 Base64 후보, 디코딩 성공
- No. 4: Hex 후보, 디코딩 성공 가능
- No. 5: TLS record header 확인, 디코딩 대상에서 제외
```

---

### sample_stream_segments.json

```json
{
  "streams": [
    {
      "stream_key": "192.168.10.5:53000-8.8.8.8:53-udp",
      "protocol": "DNS",
      "encrypted": false,
      "segments": [
        {
          "no": 1,
          "time": 0.000000,
          "payload": "001.dXNlcj1hZG.example.com",
          "position": "dns_label"
        },
        {
          "no": 2,
          "time": 0.015230,
          "payload": "002.1pbiZjbWQ9.example.com",
          "position": "dns_label"
        }
      ]
    },
    {
      "stream_key": "192.168.10.8:50120-203.0.113.10:80-tcp",
      "protocol": "HTTP",
      "encrypted": false,
      "segments": [
        {
          "no": 3,
          "time": 1.204822,
          "payload": "data=dXNlcj1hZG1pbiZjbWQ9d2hvYW1p",
          "position": "http_body"
        }
      ]
    },
    {
      "stream_key": "192.168.10.10:50121-203.0.113.30:443-tcp",
      "protocol": "TLS",
      "encrypted": true,
      "segments": []
    }
  ]
}
```

---

### sample_decode_results.json

```json
{
  "decoded_candidates": [
    {
      "stream_key": "192.168.10.8:50120-203.0.113.10:80-tcp",
      "candidate_type": "base64",
      "raw": "dXNlcj1hZG1pbiZjbWQ9d2hvYW1p",
      "decode_status": "success",
      "decoded": "user=admin&cmd=whoami",
      "score": 0.96,
      "reason": [
        "base64 charset matched",
        "decode succeeded",
        "decoded printable ratio is high"
      ]
    }
  ],
  "failed_candidates": [
    {
      "stream_key": "192.168.10.5:53000-8.8.8.8:53-udp",
      "candidate_type": "base64_fragment",
      "raw": "dXNlcj1hZG|1pbiZjbWQ9",
      "decode_status": "failed",
      "failure_type": "partial_chunk",
      "recommended_action": "collect_neighbor_segments_and_retry"
    }
  ],
  "excluded_streams": [
    {
      "stream_key": "192.168.10.10:50121-203.0.113.30:443-tcp",
      "status": "excluded",
      "reason": "encrypted_payload",
      "evidence": [
        "protocol identified as TLS",
        "TLS ClientHello header 16 03 03 detected"
      ]
    }
  ]
}
```

---

## 8. 성공 판정 기준

1. **PCAP 최소 메타를 생성할 수 있어야 한다.**

   판정 기준:

   ```text
   출력에 no, time, timestamp, src_ip, dst_ip, src_port, dst_port, protocol, length가 포함된다.
   ```

2. **암호화 세션을 디코딩 대상에서 제외해야 한다.**

   판정 기준:

   ```text
   TLS record header, ClientHello, SSH banner 등 헤더 또는 payload 근거가 있는 스트림은 excluded_streams에 포함된다.
   port 443이라는 이유만으로 제외하지 않는다.
   ```

3. **선택된 평문/부분 평문 스트림에서 인코딩 후보를 탐지해야 한다.**

   판정 기준:

   ```text
   HTTP body의 Base64 후보, TCP payload의 Hex 후보, DNS label의 Base64-like fragment 중 하나 이상을 candidates 또는 failed_candidates로 반환한다.
   ```

4. **디코딩 성공과 실패를 구분해야 한다.**

   판정 기준:

   ```text
   성공 후보는 decode_status=success와 decoded_preview를 포함한다.
   실패 후보는 decode_status=failed와 failure_type을 포함한다.
   ```

5. **실패 후보에 대해 AI가 다음 전략을 제안해야 한다.**

   판정 기준:

   ```text
   partial_chunk, padding_error, multi_stage_encoding_suspected 등 실패 유형에 대해 recommended_action이 포함된다.
   ```

6. **전체 주요 처리는 6 Step 이내에 종료되어야 한다.**

   판정 기준:

   ```text
   PCAP 메타 추출 → 스트림 선별 → payload 추출 → 인코딩/디코딩 → 실패 전략 판단 → 결과 요약
   ```

7. **요청 또는 중간 결과에 따라 Tool 조합이 달라져야 한다.**

   예시:

   ```text
   암호화 세션만 있는 경우:
   pcap_preprocess_tool → stream_filter_tool

   일반 Base64 성공 경우:
   pcap_preprocess_tool → stream_filter_tool → payload_extract_tool → encoding_decode_tool

   디코딩 실패 경우:
   pcap_preprocess_tool → stream_filter_tool → payload_extract_tool → encoding_decode_tool → decode_strategy_tool
   ```

---

## 9. 제약·확장

### 현재 설계의 한계

1. **암호화 payload는 복호화하지 않는다.**

   * TLS, SSL, SSH, VPN 등은 payload header와 프로토콜 식별 결과를 기준으로 제외한다.
   * 본 Agent는 키 없는 암호화 payload를 해독하지 않는다.

2. **위협 식별은 초기 범위에서 제외한다.**

   * Suricata, YARA, IOC 조회는 본 초기 구현 단계에 포함하지 않는다.
   * 본 단계의 목적은 위협 판정이 아니라 디코딩 가능한 payload 후보 식별이다.

3. **정식 보고서 생성 Tool은 제외한다.**

   * 초기 구현에서는 JSON/Markdown 요약만 생성한다.
   * 상세 보고서 자동화는 후속 단계로 둔다.

4. **복잡한 custom encoding 해제는 제한적이다.**

   * AI는 다음 전략을 제안할 수 있지만, 실제 디코딩 성공 여부는 검증 Tool에 의존한다.

5. **대규모 PCAP 성능 최적화는 별도 과제이다.**

   * 초기 구현은 Mock 데이터와 소규모 PCAP을 기준으로 설계한다.

---

### Multi Agent 확장 지점

다음 주 Multi Agent로 확장한다면 다음과 같이 역할을 분리할 수 있다.

1. **Metadata Agent**

   * PCAP에서 No, Time, Timestamp, IP, Port, Protocol 등 최소 메타를 추출한다.

2. **Stream Filter Agent**

   * 암호화 세션을 제외하고 payload 분석 대상 스트림을 선별한다.

3. **Payload Decode Agent**

   * Base64, Base32, Hex, URL encoding, gzip/zlib, XOR 후보를 탐지하고 디코딩한다.

4. **Decode Strategy Agent**

   * 디코딩 실패 또는 모호한 결과에 대해 padding 보정, 주변 segment 수집, 다단계 디코딩 여부를 판단한다.

5. **Threat Detection Agent**

   * 후속 단계에서 Suricata, YARA, IOC 조회를 수행한다.

---

### 장기 상태·메모리가 필요해지는 시나리오

1. **정상 encoded parameter 기억**

   * 특정 업무 시스템에서 반복적으로 등장하는 정상 Base64 parameter를 기억하여 오탐을 줄인다.

2. **분석가 피드백 반영**

   * 분석가가 “이 유형은 정상” 또는 “이 유형은 조사 가치 있음”으로 표시한 결과를 다음 분석 우선순위에 반영한다.

3. **반복 실패 패턴 저장**

   * 자주 실패하는 custom encoding 유형과 성공한 보정 전략을 저장한다.

4. **환경별 제외 정책 관리**

   * 조직 내부에서 정상적으로 사용하는 암호화/인코딩 패턴을 장기 상태로 관리한다.

---

## 자가 점검 체크리스트

1. **RAG만으로 풀 수 있는 문제가 아닌가?**

   * 아니다. 문서 검색이 아니라 PCAP 메타와 payload 분석 결과에 따라 Tool 호출 경로가 달라진다.

2. **Tool 설명이 LLM 관점에서 언제 쓸지 결정 가능할 만큼 구체적인가?**

   * 각 Tool에 목적, 입력, 출력, 실패 반환, 사용 조건을 명시했다.

3. **종료 조건과 실패 흐름이 둘 다 명시됐는가?**

   * PCAP 읽기 실패, 암호화 세션만 존재, payload 없음, 디코딩 후보 없음, 디코딩 실패 흐름을 명시했다.

4. **데이터셋이 실재하거나 Mock 규격이 스키마 수준으로 뚜렷한가?**

   * Mock CSV/JSON 파일 경로와 샘플 값을 제시했다.

5. **제약·확장 섹션에 다음 주 Multi Agent로 쪼갤 지점이 최소 한 개 식별됐는가?**

   * Metadata Agent, Stream Filter Agent, Payload Decode Agent, Decode Strategy Agent, Threat Detection Agent로 분리 지점을 제시했다.

```

이 버전은 제출용으로 꽤 안정적이야. 핵심은 **“위협탐지 Agent”가 아니라 “초기 payload 디코딩 전략 Agent”**로 좁혔다는 점이고, 그래서 과하지 않게 Agent 조건도 살렸어.
::contentReference[oaicite:1]{index=1}
```

[1]: https://github.com/bjc1102/ai-agent-repo/blob/main/week-6/TASK.md "ai-agent-repo/week-6/TASK.md at main · bjc1102/ai-agent-repo · GitHub"
