-- 디자인 채널 분리 — 데이터 정리 (운동 채널 GYM; / where where;_____)
--
-- ⚠️ Supabase SQL 에디터에서 **대표가 직접** 실행한다. Claude Code 는 저장만 하고 실행하지 않는다.
-- ⚠️ 이 PR(채널별 디자인) 머지 **전에** 실행할 것. 순서가 바뀌면 머지 직후 운동 영상의
--    design_config 가 비어(workout_music 행에 디자인 없음) 중앙 로고가 기본값 "PLAY LIST" 로 렌더된다.
--
-- 배경: 지금까지 디자인은 rooftop_music 행 하나를 두 채널이 같이 썼다(make_video 가 채널 없이 조회).
--       운동 채널용으로 playlist_text 를 'GYM;_____' 로 바꾼 뒤부터 where 영상도 GYM; 로 렌더됐다.
-- 정리: ① 지금 디자인 전체(GYM; 포함)를 workout_music 행으로 복사
--       ② rooftop_music 행은 playlist_text 만 'where;_____' 로 되돌림
--       (다른 필드는 DB 이력이 없어 GYM; 용으로 바뀌었는지 확인 불가 — PR 본문 참고)

-- 0) 실행 전 확인 — 두 행의 현재 로고/라벨 텍스트
select channel_id,
       design_config->>'playlist_text' as playlist_text,
       design_config->>'where_text'    as where_text,
       jsonb_typeof(design_config)     as type
from channel_status
where channel_id in ('rooftop_music', 'workout_music');
-- 기대: rooftop_music.playlist_text = 'GYM;_____', workout_music 은 비어 있음({} 또는 null)

-- 0-1) 백업 — 되돌릴 때 쓸 원본. 실행 결과(design_config 전체 JSON)를 복사해 메모장 등에 보관.
--      (새 테이블을 만들지 않는다 — 새 테이블은 GRANT 가 필요하고 여기선 불필요)
select channel_id, design_config
from channel_status
where channel_id in ('rooftop_music', 'workout_music');

-- ① 운동 채널에 현재 디자인 전체 복사 — workout_music 행은 운동 채널 1단계 SQL
--    (music_channel_axis.sql)로 이미 존재한다. UPDATE 결과가 "UPDATE 1" 이어야 한다.
--    "UPDATE 0" 이면 행이 없는 것 → 여기서 멈추고 Claude Code 에 알릴 것(② 실행 금지).
update channel_status w
set design_config = r.design_config
from channel_status r
where w.channel_id = 'workout_music'
  and r.channel_id = 'rooftop_music';

-- ② where 중앙 로고만 원복(다른 필드는 그대로)
update channel_status
set design_config = jsonb_set(design_config, '{playlist_text}', '"where;_____"'::jsonb, true)
where channel_id = 'rooftop_music';

-- ③ 검증
select channel_id,
       design_config->>'playlist_text' as playlist_text,
       design_config->>'where_text'    as where_text
from channel_status
where channel_id in ('rooftop_music', 'workout_music');
-- 기대: rooftop_music = 'where;_____', workout_music = 'GYM;_____'
--       나머지 필드(폰트·위치·색 등)는 두 행이 같음(아래로 확인 — 차이는 playlist_text 1개만)
select key
from jsonb_each((select design_config from channel_status where channel_id = 'rooftop_music')) r
full join jsonb_each((select design_config from channel_status where channel_id = 'workout_music')) w using (key)
where r.value is distinct from w.value;
-- 기대: playlist_text 1행

-- (GRANT) channel_status 는 기존 GRANT 그대로 — 신규 컬럼·테이블 없음.
