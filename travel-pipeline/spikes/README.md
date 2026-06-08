# spikes/ — 검증용 throwaway 스크립트

프로덕션 파이프라인에 연결되지 않는 **일회성 검증(spike)** 코드. 검증이 끝나면 삭제 가능.

## spike_kontext_consistency.py — 캐릭터 일관성 PoC (PR-S2 사전 검증)

작업 지시서 §3의 핵심 난제(자동 API 환경에서 캐릭터 일관성)를 **본 구현 전에** 실제
이미지로 확인한다. 방식: **캐릭터 시트 1장 + FLUX.1 Kontext Pro Multi(WaveSpeed)** 로
서로 다른 씬 3종 생성 → 동일 인물·웹툰 스타일 유지 여부 육안 확인.

### 실행

```bash
cd travel-pipeline
export WAVESPEED_API_KEY=...        # Windows: set WAVESPEED_API_KEY=...
py -m pip install httpx             # 미설치 시
py spikes/spike_kontext_consistency.py

# 이미 만든 시트가 있으면 재생성 없이 그 URL 로 씬만 생성:
py spikes/spike_kontext_consistency.py --sheet-url https://.../sheet.png

# 옵션
#   --num-images N   씬당 생성 장수(큐레이션용, 기본 2)
#   --seed N         seed 고정(>=0, 기본 랜덤)
#   --sheet-model    시트 생성 모델(기본 z-image/turbo)
```

결과는 `spikes/output/` 에 저장(이미지 + `manifest.json`). 이 폴더는 git 에 커밋되지 않음.

### 판정 기준

씬 **3장 이상에서 동일 인물**(얼굴/헤어 형태·색·시그니처 유지) + 웹툰 스타일 유지 +
이미지 내 글자 없음 → **PR-S2 방식 확정(GO)**. 흔들리면 §3 보조수단(seed 고정, 앵커
프롬프트 반복, Kontext **Max** 승급, 페이스스왑 후보정) 검토.
