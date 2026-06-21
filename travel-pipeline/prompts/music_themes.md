# 루프탑뮤직 주제 생성 가이드 (Theme Catalog · SSOT)

> 이 문서는 "주제 헌법"이다. 생성기(`music_theme`)가 **매 영상마다 이 문서를 읽고**, 코히어런트한 새 주제 1개를 랜덤으로 뽑는다.
> 평문이라 대표가 직접 편집 가능 — 장르·상황·무드 팔레트를 여기서 빼고 더하면 채널 방향이 바뀐다.
> 가사가 채널의 영혼이라면, 이 문서는 **채널의 지도**다.

---

## 0. 채널 정체성
루프탑뮤직은 **단일 장르 채널이 아니다.** "운동할 때 듣는 음악", "비 오는 날 피아노", "밤에 듣는 재즈"처럼
**상황·장르·무드별 음악**을 주제마다 한 영상씩 만든다. 유튜브 안에서는 장르별 플레이리스트로 정리한다.
→ 핵심은 **다양성**. 같은 장르가 연속으로 나오면 채널이 지루해진다.

---

## 1. 출력 스키마 (생성기가 뽑아야 할 형식)
주제 1개 = JSON 1개. 다른 텍스트 없이 이 형식만 출력한다.

```json
{
  "slug": "late_night_jazz",          // 영문 소문자_스네이크 (R2/DB 키)
  "title_kr": "늦은 밤 혼자 듣는 재즈",   // 유튜브 제목용 한국어
  "genre": "재즈",
  "situation": "늦은 밤",
  "mood": "잔잔·세련",
  "type": "instrumental",             // "vocal" | "instrumental"
  "style_prompt": "smooth late-night jazz, brushed drums, upright bass, soft piano, instrumental, 70 BPM, dim city lights mood",
  "lyric_tone": null,                 // vocal일 때만 한 줄, instrumental은 null
  "track_count": 8
}
```

> ⚠️ 위 `late_night_jazz`는 **형식 예시일 뿐**이다. 실제로는 매번 **새 slug·새 주제**를 생성한다 — 이 예시(또는 7번의 예시)를 그대로 베끼지 말 것.

---

## 2. 팔레트 (여기서 골라 조합)

### 장르
시티팝 · 피아노 · 재즈 · 로파이(lo-fi) · 재즈힙합(jazz-hop) · 힙합 · R&B · K-R&B/한국 감성 · 소울/펑크 · 빈티지 소울/모타운 · EDM/하우스 · 신스웨이브 · 보사노바 · 어쿠스틱/포크 · 앰비언트 · 국악 퓨전 · 클래식 크로스오버

### 상황 (use-case)
운동 · 공부·집중 · 독서 · 코딩·몰입(deep work) · 일할 때 · 드라이브 · 출근길·아침 · 퇴근길 · 잠들기 전 · 새벽 감성 · 비 오는 날 · 주말 아침 · 카페 · 데이트·로맨틱 저녁 · 불멍·캠핑 · 청소·집안일 · 여행 · 요리 · 명상/요가 · 파티

### 무드 (에너지·색)
신남(업비트) · 그루비 · 세련 · 청량(상쾌) · 잔잔 · 차분 · 몽환 · 따뜻 · 로맨틱 · 쓸쓸·회상 · 시네마틱

---

## 3. 보컬 / 연주 라우팅
- **연주(instrumental) 위주**: 피아노, 재즈, 로파이, 재즈힙합, 앰비언트, 클래식, 보사노바(대개), 국악 퓨전(대개)
- **보컬(vocal) 가능**: 시티팝, 힙합, R&B, K-R&B, 소울/펑크, 빈티지 소울/모타운, 팝, 어쿠스틱
- 일부는 둘 다 가능 — 무드·상황에 맞춰 고른다.
- **연주는 가사 생성 비용 0** (Suno instrumental). 보컬만 가사 헌법을 탄다.

---

## 4. 코히어런스 규칙 (말 되는 조합만)
어울리는 장르×상황×무드만 뽑는다. 모순 조합은 절대 금지.

| 상황 | 어울리는 무드 | 어울리는 장르 |
|---|---|---|
| 운동 · 파티 · 청소·집안일 | 신남 · 그루비 · 청량 | EDM/하우스, 신나는 시티팝, 소울/펑크, 모타운 |
| 공부·집중 · 독서 · 코딩·몰입 · 일할 때 · 잠들기 전 · 명상/요가 | 잔잔 · 차분 · 몰입 | 피아노, 앰비언트, 로파이, 재즈힙합 (연주) |
| 새벽 감성 · 비 오는 날 · 퇴근길 | 쓸쓸·회상 · 몽환 | 로파이, 피아노, R&B, K-R&B, 잔잔 시티팝 |
| 드라이브 · 출근길·아침 | 그루비 · 세련 · 청량 | 시티팝, 신스웨이브, 펑크 |
| 카페 · 주말 아침 · 요리 | 따뜻 · 편안 | 보사노바, 어쿠스틱, 가벼운 재즈, 모타운 |
| 데이트·로맨틱 저녁 | 로맨틱 · 세련 | 재즈, R&B, K-R&B, 보사노바 |
| 불멍·캠핑 · 여행 | 따뜻 · 차분 · 시네마틱 | 어쿠스틱, 앰비언트, 국악 퓨전 |

**❌ 금지 예**: 수면 EDM, 운동 앰비언트, 명상 힙합 — 상황과 에너지가 충돌하면 안 된다.

---

## 5. 다양성 규칙 (랜덤이 지루해지지 않게)
- **최근 10개** 주제와 **장르가 겹치지 않게** 뽑는다.
- **같은 상황 연속 금지.**
- **무드·에너지도 분산한다** — 최근 주제가 잔잔·차분 위주면 신남·청량을 섞고, 그 반대도 마찬가지. *장르만 다르고 다 "늦은 밤 잔잔"이면 안 된다.*
- 장르를 골고루 순환시킨다 (한 장르가 며칠씩 반복되면 안 됨).
- 같은 조합(slug)이 이미 있으면 다시 뽑는다.

---

## 6. style_prompt 작성법 (Suno용 · 영어)
`장르 + 무드 + 핵심 악기 + 보컬여부/톤 + BPM감 + 한 줄 분위기` 순으로.
- 연주는 반드시 **"instrumental"** 명시.
- 보컬은 **명료도 표현 필수**: `clear, present, polished vocals` 류로 반주에 안 묻히게.
- ⚠️ **성별(male/female)은 style_prompt에 넣지 않는다** — 성별은 produce가 곡마다 랜덤
  주입한다. 생성기는 톤·악기·명료도만 쓰고 성별 단어(female/male)는 뺀다.
- 좋은 예: `upbeat city pop, groovy slap bass, bright synths, clear present polished vocals, 112 BPM, neon Tokyo night drive`
- 나쁜 예: `nice music, chill` (장르·악기 없음)

---

## 7. 좋은 예 / 나쁜 예

### ✅ 좋은 예
```json
{ "slug": "workout_citypop", "title_kr": "운동할 때 듣는 신나는 시티팝",
  "genre": "시티팝", "situation": "운동", "mood": "신남·그루비", "type": "vocal",
  "style_prompt": "high-energy city pop, driving bass, punchy drums, bright synths, energetic clear present polished vocals, 124 BPM",
  "lyric_tone": "땀나게 달리는 순간의 자기긍정 — 응원하되 뻔한 구호는 금지, 구체적 장면으로", "track_count": 8 }
```
```json
{ "slug": "rainy_piano", "title_kr": "비 오는 날 듣는 피아노",
  "genre": "피아노", "situation": "비 오는 날", "mood": "차분·몽환", "type": "instrumental",
  "style_prompt": "gentle solo piano, soft rain ambience, reverb, instrumental, 60 BPM, melancholic window mood",
  "lyric_tone": null, "track_count": 10 }
```
```json
{ "slug": "gugak_fusion_focus", "title_kr": "집중할 때 듣는 국악 퓨전",
  "genre": "국악 퓨전", "situation": "코딩·몰입", "mood": "차분·몽환", "type": "instrumental",
  "style_prompt": "modern Korean fusion, gayageum, daegeum flute, lo-fi beats, ambient pads, instrumental, 75 BPM, calm focus",
  "lyric_tone": null, "track_count": 8 }
```
```json
{ "slug": "date_night_krnb", "title_kr": "둘만의 밤, 감성 R&B",
  "genre": "K-R&B", "situation": "데이트·로맨틱 저녁", "mood": "로맨틱·세련", "type": "vocal",
  "style_prompt": "smooth Korean R&B, warm Rhodes, soft trap drums, intimate clear present polished vocals, 85 BPM, candlelit night",
  "lyric_tone": "둘 사이의 구체적 순간(손끝·눈빛·침묵)으로 — '사랑해'를 직접 쓰지 말고 장면으로", "track_count": 8 }
```

### ❌ 나쁜 예
- `{ "situation": "잠들기 전", "genre": "EDM", "mood": "신남" }` → 상황·에너지 충돌
- `slug`이 한글이거나 공백 포함
- `style_prompt`에 장르·악기 없이 무드 단어만

---

## 8. 가사 연동 (type=vocal일 때만)
- 보컬 주제는 `lyric_tone` 한 줄을 **가사 헌법(`lyrics_guidelines.md`)에 추가 컨텍스트로** 넘긴다.
- 헌법의 공통 원칙(메시지 우선 · 구체 이미지 · 여운 · 클리셰 금지)은 **모든 장르 공통**.
- 단 목소리(voice)는 장르에 맞춘다: 힙합=라임·플로우·구체 서사, 시티팝=세련된 도시 감성, R&B/K-R&B=감각적 디테일, 어쿠스틱=담백한 고백, 소울/모타운=따뜻한 그루브.

---

## 9. 운영 메모
- 이 문서는 SSOT. 장르/상황/무드를 늘리면 채널이 넓어지고, 줄이면 좁아진다.
- 새 장르를 추가할 땐 4번(코히어런스)·6번(style_prompt 예시)도 같이 채운다.
- 연주:보컬 비율은 팔레트와 다양성 규칙이 자연스럽게 정한다 (대략 연주가 더 많게 나온다 — 비용도 0).
- **자연음/화이트노이즈(빗소리·장작·파도)는 향후 확장**: Suno 음악이 아니라 별도 효과음 생성(Suno Sounds Generation) 경로가 필요. 지금 팔레트엔 음악 장르만 둔다.
