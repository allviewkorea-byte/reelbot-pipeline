-- music_jobs — 음악 파이프라인 작업 추적(운영 가시성, 작업지시서 #36)
-- 진행 중/완료/실패 작업을 DB 에 영구 기록 → 페이지 이동·기기 전환에도 상태 유지.
-- 인메모리 _JOBS(재시작 시 소실)와 병행: 이 테이블이 교차 가시성의 단일 진실.
--
-- ⚠️ Supabase SQL 에디터에서 1회 수동 실행(레포에 마이그레이션 러너 없음).
-- GRANT 누락 시 PostgREST 401 — 반드시 마지막 grant 까지 실행.

create table if not exists public.music_jobs (
  id uuid primary key default gen_random_uuid(),
  job_id text not null unique,            -- 외부 job id (manual_render/rerender/cron)
  type text not null,                     -- 'manual_render' | 'cron' | 'rerender'
  mix_id text,                            -- 연관 music_uploads.mix_id (있으면)
  status text not null default 'queued',  -- queued|running|completed|failed
  step text,                              -- 현재 단계 (STEPS 중 1개)
  step_progress int default 0,            -- 0~100 진행률
  steps_completed jsonb default '[]'::jsonb,  -- 완료된 단계 배열
  error_message text,                     -- 실패 시 메시지
  metadata jsonb default '{}'::jsonb,     -- track_count / mood 등 부가 정보
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  completed_at timestamptz                -- 완료/실패확인(dismiss) 시각
);

create index if not exists music_jobs_status_idx on public.music_jobs(status);
create index if not exists music_jobs_created_at_idx on public.music_jobs(created_at desc);

grant all on table public.music_jobs to service_role, anon, authenticated;
