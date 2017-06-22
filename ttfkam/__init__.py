from multicorn import ForeignDataWrapper
import re
from subprocess import Popen, PIPE

# wrapper 'geekspeak.FindWrapper',
# options(
#   mimetype='/usr/bin/file -b -i {}'  # mime type
#   season='s(?P<season>\\d{2})e(?P<episode>\\d{2})(?:  -  (?P<name>.*?))\.(?P<extension>[^.]{3,4})'
# )
class FindWrapper(ForeignDataWrapper):

  def __init__(self, options, columns):
    super(FindWrapper, self).__init__(options, columns)
    self._root = FindWrapper.__extract_root_directory(options)
    self._handlers = {}
    self._patterns = []
    self.__init_handlers(self._handlers, self._patterns, options, columns)

  def execute(self, quals, columns):
    handlers = [
      [],  # builtins
      [],  # patterns
      [],  # extensions
    ]
    path_index = -1
    debug_quals = None
    for colname in columns:  # organize our columns into query types, e.g., patterns
      if colname == 'debug_quals':
        debug_quals = str(quals)
        continue
      handler = self._handlers[colname]
      handlers[handler[0]].append((colname, handler[1], handler[2], handler[3]))
      if colname == 'path' and handler[0] == 0:  # if we've got a path and it's not aliased
        path_index = len(handlers[0])  # track it for patterns

    builtins = list(map((lambda h: h[1]), handlers[0]))  # build up our list of patterns

    patterns = {}  # patterns need a path
    if len(handlers[1]) > 0:
      for p in handlers[1]:
        pattern_id = p[1]
        patterns[pattern_id] = self._patterns[pattern_id]
      if path_index == -1:  # otherwise, add it to the query patterns
        builtins.append('%P')
        path_index = len(handlers[0])

    # set up program arguments
    args = ['/usr/bin/find', '-O3', self._root,
            '-regextype', 'posix-egrep', '-ignore_readdir_race']

    # TODO: quals disabled until functionality complete
    for qual in quals:  # process quals to reduce raw find output
      if not qual.is_list_operator:  # Can't convert from array syntax to GNU find
        args += self._handlers[qual.field_name][2](qual, self._root) or EMPTY_LIST

    args += [ '-printf', US.join(builtins) + '\n' ]  # append query patterns to program args

    extensions = list(map((lambda h: h[1]), handlers[2]))  # set up extension queries
    for extension in extensions:
      suffix = [';'] if '{}' in extension else ['{}', ';']
      args += ['-exec'] + extension.split(' ') + suffix

    proc = Popen(args, universal_newlines=True, stdout=PIPE)  # run the program
    for line in proc.stdout:  # …and get the results
      row = {}

      if debug_quals != None:
        row['debug_quals'] = debug_quals

      ext_handlers = handlers[2]  # process extensions
      for i in range(0, len(ext_handlers)):
        colname = ext_handlers[i][0]
        # each -exec comes on its own new line
        row[colname] = proc.stdout.readline().rstrip("\n\r")

      builtin_handlers = handlers[0]  # process builtins
      parts = line.rstrip("\n\r").split(US)
      for i in range(0, len(builtin_handlers)):
        colname = builtin_handlers[i][0]
        row[colname] = builtin_handlers[i][3](parts[i], self._root)

      matches = {}  # process patterns
      for pattern in patterns:
        matches.update(patterns[pattern].fullmatch(parts[path_index]).groupdict())
      for colname in list(map((lambda h: h[0]), handlers[1])):
        row[colname] = matches[colname]
      yield row

  @staticmethod
  def __extract_root_directory(options):
    if 'root_directory' in options:
      root = options['root_directory']
      del options['root_directory']
      if root[-1:] != '/':
        root += '/'
      return root
    else:
      log_to_postgres(logging.ERROR, 'No root_directory specified in options')

  def __init_handlers(self, handlers, patterns, options, columns):
    for option in options:
      if option not in columns:
        log_to_postgres(logging.ERROR, 'Invalid column: ' + option)
        return
      if option in handlers:
        log_to_postgres(logging.ERROR, 'Column option defined more than once: ' + option)
        return
      value = options[option]
      if value[0] in ('/', '~'):  # executable
        handlers[option] = (2, value, noop_qual, default_serializer)
      elif '(' not in value:  # not a regex pattern, therefore an alias
        if value in BUILTINS:
          handlers[option] = as_handler(BUILTINS[value])
        else:
          log_to_postgres(logging.ERROR, 'Invalid alias: ' + value)
          return
      else:  # assumed to be a pattern unless an error proves otherwise
        if '(?P<' not in value:  # if there's no group name
          # use the option name as the group name
          value = value.replace('(', '(?P<%s>' % option, 1)
        value = (self._root + value) if value[0] != '^' else (self._root + value[1:])
        colnames = [m.group(1) for m in PATTERN_RE.finditer(value) if m]
        if option in colnames:
          for colname in colnames:
            if colname in handlers:
              log_to_postgres(logging.ERROR, 'Column defined more than once: ' + value)
              return
            handlers[colname] = (1, len(patterns), noop_qual, default_serializer)
          try:
            patterns.append(re.compile(value))
          except re.error:
            log_to_postgres(logging.ERROR, 'Invalid pattern: ' + value)
            return
        else:
          log_to_postgres(logging.ERROR, 'Invalid column: ' + option)
          return
    for colname in columns:
      if colname in handlers:
        continue  # Already handled by aliasing
      elif colname in BUILTINS:
        handlers[colname] = as_handler(BUILTINS[colname])
      elif colname == 'debug_quals':
        continue  # handle by name
      else:
        log_to_postgres(logging.ERROR, 'Invalid column: ' + colname)
        return

def as_handler(builtin):
  qualifier = builtin[1]
  serializer = default_serializer if len(builtin) < 3 else builtin[2]
  return (0, builtin[0], qualifier, serializer)

PATTERN_RE = re.compile('\(\?P<\s*([^ \)]+)\s*>')

EMPTY_LIST = []

def time_serializer(val, path):
  return val.replace('+', ' ')

def dir_serializer(val, path):
  plen = len(path)
  return val[plen:] if plen < len(val) else ''

def default_serializer(val, path):
  return val if len(val) > 0 else None

def time_qual(name):
  def q(qual, path):
    if qual.operator == '=':
      return ['-%smin' % name, '0']
    elif qual.operator in ('<', '<='):
      return ['-not', '-newer%st' % name, qual.value]
    elif qual.operator in ('>', '>='):
      return ['-newer%st' % name, qual.value]
  return q

def num_qual(param):
  def q(qual, path):
    if qual.operator == '=':
      return [param, str(qual.value)]
  return q

def name_qual(qual, path):
  if qual.operator == '~~':     # LIKE
    return ['-name', qual.value.replace('%', '*')]
  elif qual.operator == '~~*':  # ILIKE
    return ['-iname', qual.value.replace('%', '*')]
  elif qual.operator == '!~~':
    return ['-not', '-name', qual.value.replace('%', '*')]
  elif qual.operator == '!~~*':
    return ['-not', '-iname', qual.value.replace('%', '*')]

def depth_qual(qual, path):
  if qual.operator == '=':
    depth = str(qual.value)
    return ['-mindepth', depth, '-maxdepth', depth]
  elif qual.operator == '!=':
    return ['-not', '-depth', str(qual.value)]
  elif qual.operator == '<':
    return ['-maxdepth', str(qual.value)]
  elif qual.operator == '>':
    return ['-mindepth', str(qual.value)]
  elif qual.operator == '<=':
    return ['-maxdepth', str(qual.value + 1)]
  elif qual.operator == '>=':
    return ['-mindepth', str(qual.value - 1)]

def fs_qual(name, path):
  if qual.operator == '=':
    return ['-fstype', qual.value]
  elif qual.operator == '!=':
    return ['-not', '-fstype', qual.value]

def hardlink_qual(qual, path):
  if qual.operator == '=':
    return ['-links', str(qual.value)]
  elif qual.operator == '<':
    return ['-links', '-' + str(qual.value)]
  elif qual.operator == '>':
    return ['-links', '+' + str(qual.value)]
  elif qual.operator == '<=':
    return ['-links', '-' + str(qual.value + 1)]
  elif qual.operator == '>=':
    return ['-links', '+' + str(qual.value - 1)]

def symlink_qual(qual, path):
  if qual.operator == '~~':
    return ['-lname', qual.value.replace('%', '*')]
  elif qual.operator == '~~*':
    return ['-ilname', qual.value.replace('%', '*')]
  elif qual.operator == '!~~':
    return ['-not', '-lname', qual.value.replace('%', '*')]
  elif qual.operator == '!~~*':
    return ['-not', '-ilname', qual.value.replace('%', '*')]

def path_qual(qual, path):
  value = path + qual.value
  if qual.operator == '~~':     # LIKE
    return ['-regex', value.replace('%', '.*')]
  elif qual.operator == '~~*':  # ILIKE
    return ['-iregex', value.replace('%', '.*')]
  elif qual.operator == '!~~':
    return ['-not', '-regex', value.replace('%', '.*')]
  elif qual.operator == '!~~*':
    return ['-not', '-iregex', value.replace('%', '.*')]
  else:
    value = '.*' + value if value[0] == '^' else value[1:]
    value = value + '.*' if value[-1] != '$' else value[:-1]
    if qual.operator == '~':
      return ['-regex', value]
    elif qual.operator == '~*':
      return ['-iregex', value]
    elif qual.operator == '!~':
      return ['-not', '-regex', value]
    elif qual.operator == '!~*':
      return ['-not', '-iregex', value]

def type_qual(qual, path):
  if qual.operator == '=':
    return ['-type', qual.value[0]]

def owner_qual(param):
  def q(qual, path):
    if qual.operator == '=':
      return [param, qual.value]
  return q

def size_qual(qual, path):
  if qual.operator == '=':
    return ['-size', '%dc' % (qual.value)]
  elif qual.operator == '<':
    return ['-size', '-%dc' % (qual.value)]
  elif qual.operator == '>':
    return ['-size', '+%dc' % (qual.value + 1)]
  elif qual.operator == '<=':
    return ['-size', '-%dc' % (qual.value + 1)]
  elif qual.operator == '>=':
    return ['-size', '+%dc' % (qual.value)]

def noop_qual(qual, path):
  return EMPTY_LIST

US = '\t'  # builtin pattern unit separator

BUILTINS = {
  'accessed': ('%A+', time_qual('a'), time_serializer),
  'changed': ('%C+', time_qual('c'), time_serializer),
  'depth': ('%d', depth_qual),
  'devnum': ('%D', noop_qual),
  'dirname': ('%h', path_qual, dir_serializer),
  'eperms': ('%M', noop_qual),
  'filename': ('%f', name_qual),
  'filesystem': ('%F', fs_qual),
  'fullpath': ('%p', noop_qual),
  'gid': ('%G', num_qual('-gid')),
  'group': ('%g', owner_qual('-group')),
  'hardlinks': ('%n', hardlink_qual),
  'inum': ('%i', num_qual('-inum')),
  'modified': ('%T+', time_qual('m'), time_serializer),
  'path': ('%P', path_qual),
  'perms': ('%m', noop_qual),
  'selinux': ('%Z', noop_qual),
  'size': ('%s', size_qual),
  'sparseness': ('%S', noop_qual),
  'symlink': ('%l', symlink_qual),
  'type': ('%Y', type_qual),
  'uid': ('%U', num_qual('-uid')),
  'user': ('%u', owner_qual('-user'))
  }
