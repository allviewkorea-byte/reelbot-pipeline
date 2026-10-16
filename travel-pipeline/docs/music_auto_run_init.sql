-- 음악 자동 회차(PR-2a) — 운동 채널 초기값 + where 자동 생산 off
--
-- ⚠️ Supabase SQL 에디터에서 **대표가 직접** 실행한다. Claude Code 는 저장만 하고 실행하지 않는다.
-- ⚠️ 이 SQL 은 머지의 선행 조건이 아니다(신규 컬럼·테이블 없음). 코드는 값이 없어도 안전 기본값으로 돈다
--    (공개 시각 기본 [6,18]). 같은 값은 머지·배포 후 운동 메인 화면 버튼으로도 넣을 수 있다.
-- ⚠️ 시점: 오늘 18시대 회차의 T+3시간이 지난 뒤(KST 22:00 이후)에 운동 is_active=true 상태로 배포돼야
--    오늘 18시대 회차가 "늦은 회차 즉시 시작"으로 돌지 않는다. 22:00 전에 배포한다면 이 SQL 을
--    22:00 이후에 실행하거나, 운동 화면 가동을 22:00 이후에 켤 것.

-- 0) 실행 전 확인
select channel_id, is_active, mode, synthetic_media, daily_cap, track_count,
       channel_config->'publish_hours' as publish_hours
from channel_status
where channel_id in ('rooftop_music', 'workout_music');

-- 1) 운동 채널 초기값 — "UPDATE 1" 이어야 한다(행은 운동 채널 1단계 SQL 로 이미 있음).
--    channel_config 의 다른 키(슬로건·소셜·AI 명시)는 || 로 보존하고 publish_hours 만 넣는다.
update channel_status
set is_active = true,
    mode = 'auto',
    synthetic_media = true,
    daily_cap = 2,
    track_count = 10,
    channel_config = coalesce(channel_config, '{}'::jsonb) || '{"publish_hours": [6, 18]}'::jsonb,
    updated_at = now()
where channel_id = 'workout_music';

-- 2) where 자동 생산 off — 화면 "가동 중" 표시를 끈다.
--    (코드도 where 를 자동 회차 대상에서 제외하므로 이 줄이 없어도 where 는 자동 생산되지 않는다.)
update channel_status
set is_active = false, updated_at = now()
where channel_id = 'rooftop_music';

-- 3) 검증
select channel_id, is_active, mode, synthetic_media, daily_cap, track_count,
       channel_config->'publish_hours' as publish_hours
from channel_status
where channel_id in ('rooftop_music', 'workout_music');
-- 기대: workout_music = true / auto / true / 2 / 10 / [6, 18]
--       rooftop_music = is_active false (나머지 그대로)

-- (GRANT) channel_status 기존 GRANT 그대로 — 신규 컬럼·테이블 없음.
