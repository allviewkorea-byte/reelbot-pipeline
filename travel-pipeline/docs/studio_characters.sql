-- 캐릭터 스튜디오(채널 공통) — 캐릭터 + 역할별 기준 이미지(A0-1).
-- 쇼츠 hero(cast/{channel}/… R2 JSON)·백곰(sayeon_cast)과 완전히 분리된 새 테이블.
-- 이미지 원본은 R2 캐릭터 버킷 characters/{character_id}/{role}/… 에 두고 여기엔 키·URL만.
--
-- ⚠️ 실행 순서: 이 SQL 을 Supabase SQL Editor 에서 먼저 실행 → GRANT 확인 → PR 머지.
-- 여러 번 실행해도 안전(if not exists / on conflict do nothing).

create table if not exists studio_characters (
  id          text primary key check (id ~ '^[a-z][a-z0-9_]{1,31}$'),  -- 'chaei'
  name        text not null,                                           -- '채이'
  channel_id  text,                                                    -- 'insta_chaei' (없어도 됨)
  bible       jsonb not null default '{}'::jsonb,                      -- 나이·키·체형·헤어·분위기·규칙
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists studio_character_refs (
  id            bigint generated always as identity primary key,
  character_id  text not null references studio_characters(id) on delete cascade,
  role          text not null check (role ~ '^[a-z0-9][a-z0-9_]{1,39}$'),  -- '01_face','02_body','hair_01_straight','pose_walk'
  status        text not null default 'candidate'
                check (status in ('candidate', 'confirmed', 'discarded')),
  source        text not null check (source in ('upload', 'generated')),
  r2_key        text not null,
  url           text not null,
  w             int,
  h             int,
  prompt        text,                                                  -- 생성 이미지만(A0-3)
  parent_ref_id bigint references studio_character_refs(id) on delete set null,  -- 기준으로 쓴 얼굴 등
  batch_id      text,                                                  -- 같은 번에 뽑은 후보 묶음(A0-3)
  created_at    timestamptz not null default now(),
  confirmed_at  timestamptz
);

-- 역할마다 확정은 최대 1장.
create unique index if not exists studio_character_refs_one_confirmed
  on studio_character_refs (character_id, role) where status = 'confirmed';
create index if not exists studio_character_refs_char_status
  on studio_character_refs (character_id, status, role);

grant all on table studio_characters, studio_character_refs to service_role, anon, authenticated;

-- 채이 기본 행(기존 13장 가져오기 대상). 이미 있으면 그대로 둔다.
insert into studio_characters (id, name, channel_id, bible) values (
  'chaei', '채이', 'insta_chaei',
  '{"age": 24, "height_cm": 172, "origin": "original virtual person",
    "hair": "black, long (fixed)",
    "face_policy": "content hides the face (phone in mirror selfie / framed from the shoulders down); profile photo only shows the face"}'::jsonb
) on conflict (id) do nothing;
