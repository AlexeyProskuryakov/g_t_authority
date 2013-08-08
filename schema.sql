drop table if exists entries;

create table entries (
  e_id integer primary key autoincrement,
  email text ,
  twitter_id int,
  visit_time date,
  e_hash text,
  e_identity text not null ,
  CONSTRAINT c_identity UNIQUE (e_identity)
);
