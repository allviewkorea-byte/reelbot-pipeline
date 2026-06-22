-- #30 음악 채널 곡수(track_count) 설정 — channel_status 에 컬럼 추가.
-- 대시보드 '곡수: 1/2/3/5/8' 토글이 channel_status(channel_id='rooftop_music') 에 저장하고,
-- 음악 cron(_run_produce)이 이 값을 읽어 run_theme(n=track_count) 로 생성한다.
-- Supabase SQL Editor 에서 실행. 즉시 반영(재배포 불필요).

alter table public.channel_status
  add column if not exists track_count int default 1;

-- GRANT 재확인(신규 컬럼은 테이블 권한 상속이나, 누락 시 401 방지용 재적용).
grant all on table public.channel_status to service_role, anon, authenticated;
