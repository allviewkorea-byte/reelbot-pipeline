-- 운동 채널 1단계 — music_tracks / music_jobs 에 채널 축(channel) 추가.
--
-- ⚠️ Supabase SQL 에디터에서 **대표가 직접·먼저** 1회 실행한다(레포에 마이그레이션 러너 없음).
--    Claude Code 는 이 파일을 저장만 하고 실행하지 않는다.
--
-- 배경: music_store.find_unused_track(genre) 이 used=false 트랙을 **장르만으로** 찾는다.
--       채널 분리 없이 운동 채널을 돌리면 운동용 EDM 이 where;_____ 영상에 섞여 들어간다
--       (반대도 마찬가지). 크레딧 낭비가 아니라 잘못된 곡이 업로드되는 사고다.
--
-- ★ default 'rooftop_music' 이 회귀 방지의 핵심 — 기존 트랙·작업이 전부 where 채널로
--   자동 백필되므로 where 채널 동작이 바뀌지 않는다.

-- 1) 트랙·작업에 채널 축 추가. 기존 데이터는 전부 where 채널로 백필.
alter table music_tracks add column if not exists channel text not null default 'rooftop_music';
alter table music_jobs   add column if not exists channel text not null default 'rooftop_music';

-- 2) 재활용 풀 조회용 인덱스 (channel + used + genre 로 찾는다)
create index if not exists music_tracks_channel_idx on music_tracks (channel, used, genre);
create index if not exists music_jobs_channel_idx   on music_jobs (channel, created_at desc);

-- 3) GRANT (신규 컬럼 필수 — 누락 시 PostgREST 401 permission denied)
grant all on table music_tracks to service_role, anon, authenticated;
grant all on table music_jobs   to service_role, anon, authenticated;

-- 4) 운동 채널 행 생성. track_count 기본 1(과금 최소).
--    ※ channel_status.channel_id 에 PK/unique 제약이 있어야 on conflict 가 성립한다.
--      레포에 channel_status 의 CREATE TABLE 문이 없어 DDL 로는 확인 불가하나,
--      운영 코드가 channel_id 를 conflict target 으로 upsert 하고 정상 동작하므로
--      (music_channel.set_design_config 의 ?on_conflict=channel_id,
--       src/lib/supabase.ts 의 .upsert(row, { onConflict: "channel_id" }))
--      제약은 존재한다. 실행 전 아래로 1초에 재확인 가능:
--        select conname, contype from pg_constraint
--        where conrelid = 'channel_status'::regclass and contype in ('p','u');
insert into channel_status (channel_id, track_count)
values ('workout_music', 1)
on conflict (channel_id) do nothing;
