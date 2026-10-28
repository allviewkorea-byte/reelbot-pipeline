-- 매일 점검 리포트 + 유튜브 성과 (2026-10-28)
create table if not exists ops_reports (
  date        date primary key,
  data        jsonb not null default '{}'::jsonb,   -- 수집 원본(상태·작업·업로드·컬렉션·유튜브 요약)
  summary     jsonb not null default '{}'::jsonb,   -- {level, headline, issues[], good[]}
  created_at  timestamptz not null default now()
);
grant all on table ops_reports to service_role, anon, authenticated;

create table if not exists yt_video_stats (
  video_id      text not null,
  date          date not null,
  channel       text not null,
  title         text,
  genre         text,
  mood          text,
  uploaded_at   timestamptz,
  views         bigint not null default 0,
  likes         bigint not null default 0,
  comments      bigint not null default 0,
  avg_view_sec  numeric,          -- 평균 시청 시간(초) — 애널리틱스 권한 있을 때
  avg_view_pct  numeric,          -- 평균 시청 비율(%) = 시청 지속률
  created_at    timestamptz not null default now(),
  primary key (video_id, date)
);
create index if not exists yt_video_stats_channel_date on yt_video_stats (channel, date desc);
grant all on table yt_video_stats to service_role, anon, authenticated;
