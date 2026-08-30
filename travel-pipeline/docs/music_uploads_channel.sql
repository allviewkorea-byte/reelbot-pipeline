-- 운동 채널 2단계 — music_uploads 에 채널 축(channel) 추가.
--
-- ⚠️ Supabase SQL 에디터에서 **대표가 직접·먼저** 1회 실행한다.
--    Claude Code 는 이 파일을 저장만 하고 실행하지 않는다.
--
-- 배경: 1단계(music_channel_axis.sql)는 music_tracks·music_jobs 만 다뤘다. 검토 대기 큐
--       (music_uploads)는 채널이 없어 운동 채널 영상과 where 영상이 같은 큐에 섞인다.
--       사이드바 "검토 N" 배지도 이 테이블에서 나오므로 채널별로 갈리지 않는다.
--
-- ★ default 'rooftop_music' 이 회귀 방지의 핵심 — 기존 행이 전부 where 로 백필된다.
--   구조는 1단계와 동일하다(music_uploads 도 upsert 키가 mix_id 로 music_tracks 와 같은 형태).

-- 0) 마이그레이션 전 행 수 확인(백필 검증용 — 실행 전에 먼저 돌려 숫자를 적어둘 것).
select count(*) as total_before from music_uploads;
select status, count(*) as cnt from music_uploads group by status order by cnt desc;

-- 1) 채널 축 추가. 기존 행은 전부 where 채널로 백필.
alter table music_uploads add column if not exists channel text not null default 'rooftop_music';

-- 2) 조회용 인덱스 — list_pending(status+channel+최신순) / count_today_kst(channel+created_at).
create index if not exists music_uploads_channel_status_idx
  on music_uploads (channel, status, created_at desc);

-- 3) GRANT (신규 컬럼 필수 — 누락 시 PostgREST 401 permission denied)
grant all on table music_uploads to service_role, anon, authenticated;

-- 4) 백필 검증 — total_after 가 0번의 total_before 와 같아야 하고,
--    rooftop_music 행 수도 같아야 한다(신규 컬럼이 전 행에 채워졌는지 확인).
select count(*) as total_after from music_uploads;
select channel, count(*) as cnt from music_uploads group by channel order by cnt desc;
-- 기대: rooftop_music = total_before, 그 외 채널 0건
