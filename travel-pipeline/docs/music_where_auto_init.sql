-- where 채널(rooftop_music) 자동 회차 켜기 — 초기값
--
-- ⚠️ Supabase SQL 에디터에서 **대표가 직접** 실행한다. Claude Code 는 저장만 하고 실행하지 않는다.
-- ⚠️ 머지 선행 조건이 아니다(신규 컬럼·테이블 없음). 이 SQL 을 실행하는 순간 where 자동 회차가 켜진다.
--
-- ⚠️ 실행 시점(중요) — 늦은 회차 즉시 실행 문제:
--    자동 회차는 "제작 시작 시각(T−120분)이 지났고 T+3시간 전"인 회차를 바로 시작한다.
--    where 회차는 08시대·21시대이므로 아래 시간대에 is_active=true 가 되면 그 회차가 즉시 제작되고,
--    끝나는 대로(T 가 지났으면) 바로 공개된다.
--      · 06:00 ~ 11:59 KST 사이 실행 → 오늘 08시대 회차가 즉시 시작될 수 있음
--      · 19:00 ~ 23:59 KST 사이 실행 → 오늘 21시대 회차가 즉시 시작될 수 있음
--    → 안전한 실행 시간: **12:00 ~ 18:59 KST** 또는 **00:00 ~ 05:59 KST**.
--    (운동 회차 제작 구간 04~07시·16~19시와 겹치면 where 는 운동 제작이 끝날 때까지 T 까지 기다린다.)
--
-- 백엔드 배포(#where PR 머지) 전에 실행해도 된다 — 옛 코드는 where 를 자동 회차에서 제외한다.
-- 단, 배포 후 첫 tick 에 위 "늦은 회차" 규칙이 적용되므로 배포 시점도 같은 시간대를 지킬 것.

-- 0) 실행 전 확인
select channel_id, is_active, mode, synthetic_media, daily_cap, track_count,
       channel_config->'publish_hours' as publish_hours
from channel_status
where channel_id in ('rooftop_music', 'workout_music');

-- 1) where 초기값 — "UPDATE 1" 이어야 한다. channel_config 의 다른 키(슬로건·소셜·AI 명시)는 || 로 보존.
update channel_status
set is_active = true,
    mode = 'auto',
    synthetic_media = true,
    daily_cap = 2,
    track_count = 10,
    channel_config = coalesce(channel_config, '{}'::jsonb) || '{"publish_hours": [8, 21]}'::jsonb,
    updated_at = now()
where channel_id = 'rooftop_music';

-- 2) 검증
select channel_id, is_active, mode, synthetic_media, daily_cap, track_count,
       channel_config->'publish_hours' as publish_hours
from channel_status
where channel_id in ('rooftop_music', 'workout_music');
-- 기대: rooftop_music = true / auto / true / 2 / 10 / [8, 21]   (workout_music 은 그대로)

-- 끄려면: update channel_status set is_active = false, updated_at = now() where channel_id = 'rooftop_music';
-- (GRANT) channel_status 기존 GRANT 그대로 — 신규 컬럼·테이블 없음.
