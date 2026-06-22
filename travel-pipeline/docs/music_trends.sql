-- music_trends — Rooftop Music 트렌드 분석 인사이트(주 2회 cron 저장).
-- 레포에 마이그레이션 러너가 없으므로 Supabase SQL 에디터에서 1회 수동 실행한다.
-- ⚠️ 신규 테이블은 GRANT 필수(누락 시 PostgREST 401 permission denied).

create table if not exists music_trends (
  id             bigint generated always as identity primary key,
  analyzed_at    timestamptz default now(),
  mood_keywords  jsonb,                  -- 자주 등장하는 무드
  title_patterns jsonb,                  -- 제목 경향
  hot_situations jsonb,                  -- 인기 상황/시간대
  summary        text,                   -- 한 줄 인사이트
  raw_samples    jsonb                   -- 참고용 인기영상 제목·조회수·채널
);

-- 최신 1건("현재 트렌드") 조회용.
create index if not exists music_trends_analyzed_idx on music_trends (analyzed_at desc);

-- 🚨 GRANT — 기존 테이블과 동일 패턴(service_role / anon / authenticated).
grant all on table music_trends to service_role, anon, authenticated;
grant usage, select on all sequences in schema public to service_role, anon, authenticated;
