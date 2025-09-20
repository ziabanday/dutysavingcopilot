-- Postgres + pgvector schema (will be applied on Supabase later)
create table if not exists hts_items (
    id bigserial primary key,
    code text not null,
    description text not null,
    duty_rate text,
    chapter int,
    notes text
);

create table if not exists rulings (
    id bigserial primary key,
    ruling_id text not null,
    hts_codes text[],
    url text,
    text text,
    ruling_date date
);

create extension if not exists vector;
create table if not exists ruling_chunks (
    id bigserial primary key,
    ruling_id_fk bigint references rulings(id) on delete cascade,
    chunk_index int,
    text text,
    embedding vector(1536),
    embedding_model text,
    chunk_version text
);

create index if not exists idx_ruling_chunks_embedding on ruling_chunks using ivfflat (embedding vector_cosine_ops);
