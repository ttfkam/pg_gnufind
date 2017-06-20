# pg_gnufind
GNU find output as foreign tables. Requires python 3.3+.

## Install
On an Ubuntu system, run the following:

```bash
  $ sudo apt-get update
```

If not already installed, install PostgreSQL and required modules. Note: this FDW requires Python 3, so be sure
you install the python3 version of multicorn.

```bash
  $ sudo apt-get install postgresql-9.6 postgresql-9.6-python3-multicorn
```
Install development tools

```bash
  $ sudo apt-get install postgresql-server-dev-9.6
```
Download pg_geekspeak and run the following inside the project directory

```bash
  $ ./tests.py
```

Verify all tests pass, then install.

```bash
  $ sudo cp -r ttfkam /usr/lib/python3/dist-packages/
```

Within PostgreSQL, install the multicorn extension, create the foreign data server, and make your tables.

```sql
  -- Add the extension. This is a hard dependency. It will not work without it.
  CREATE EXTENSION multicorn;

  -- Create the foreign server. This is not a server in the traditional TCP/IP sense. This is a mapping
  -- between PostgreSQL's foreign data wrapper interface and any foreign tables you may create.
  CREATE SERVER gnufind  -- This can be any name you like, but it's best to be descriptive.
    FOREIGN DATA WRAPPER multicorn
    OPTIONS (wrapper 'ttfkam.FindWrapper');  -- Searches the default python path

  -- Now create your table. All of these columns are optional.
  CREATE FOREIGN TABLE gs.media_fdw (
    accessed timestamptz NOT NULL,  -- Last accessed (reverts to last modified if noatime is set)
    changed timestamptz NOT NULL,   -- Last changed (reverts to last modified if noctime is set)
    depth smallint NOT NULL,        -- Levels deep inside the search root
    dirname varchar,                -- Just the directory portion, omitting file
    eperms varchar NOT NULL,        -- Permissions in expanded form
    filename varchar,               -- Just the file portion, omitting directories
    filesystem varchar,             -- Filesystem type, e.g., ext4, zfs
    gid int4 NOT NULL,              -- Filesystem entry group id (see: /etc/group)
    group varchar NOT NULL,         -- Filesystem entry group name (see: /etc/group)
    hardlinks smallint NOT NULL,    -- Number of hardlinks that refer to this bag o' bytes
    inum int8 NOT NULL,             -- inode number from the filesystem
    modified timestamptz NOT NULL,  -- Last modified
    path varchar NOT NULL,          -- Path relative to the search root
    perms varchar NOT NULL,         -- Permissions in octal form
    size bigint NOT NULL,           -- Storage space used
    symlink character varying,      -- If it's a symbolic link, where it points to
    type character(1) NOT NULL,     -- Entry type, e.g., 'f' for file, 'd' for directory
    uid int4 NOT NULL,              -- Filesystem entry user id (see: /etc/passwd)
    user varchar NOT NULL,          -- Filesystem entry user name (see: /etc/passwd)

    -- Here's where it gets fun. Warning, accessing external program output hurts performance
    mime varchar,
    encoding varchar,

    -- Debugging. If you have a problem with WHERE clauses, I'll need this data to fix it.
    debug_quals text
  )
  SERVER gnufind  -- Make sure this matches your CREATE SERVER statement above
  OPTIONS (
    root_directory '/var/some/dir/to/scan/',  -- This option is mandatory!

    -- This is how the mime and encoding are gathered as listed above.
    -- You can pass in any program as long as it returns only a single line of text.
    mime '/usr/bin/file -L -b --mime-type',
    encoding '/usr/bin/file -L -b --mime-encoding'
  );
```

