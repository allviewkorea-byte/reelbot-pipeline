-- music_uploads v2 — 검토 대기 큐(#8)용 컬럼 추가.
-- music_uploads.sql(v1) 실행 후 이 파일을 Supabase SQL 에디터에서 실행한다.
-- ⚠️ 컬럼 추가 후에도 GRANT 는 유지되지만, 안전을 위해 GRANT 재실행을 권장한다.

alter table music_uploads add column if not exists status text default 'pending';   -- pending|uploaded
alter table music_uploads add column if not exists thumbnail_r2_key text;           -- 업로드된 썸네일 R2 키
alter table music_uploads add column if not exists gpt_prompt text;                 -- 썸네일 생성용 GPT 프롬프트
alter table music_uploads add column if not exists mp4_url text;                     -- 완성 영상 R2 URL
alter table music_uploads add column if not exists title_kr text;                    -- 주제 한국어 제목
alter table music_uploads add column if not exists genre text;
alter table music_uploads add column if not exists mood text;

-- 큐는 mix_id 기준 upsert(검토 대기 → 업로드 완료) 하므로 mix_id 유니크 필요.
create unique index if not exists music_uploads_mix_id_key on music_uploads (mix_id);

-- 검토 대기 조회 인덱스(status + 최신순).
create index if not exists music_uploads_status_idx on music_uploads (status, created_at desc);

-- 🚨 GRANT 재확인(컬럼 추가 후) — 기존 패턴과 동일.
grant all on table music_uploads to service_role, anon, authenticated;
