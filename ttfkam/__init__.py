from multicorn import ForeignDataWrapper
import re
from subprocess import Popen, PIPE
import json

# wrapper 'geekspeak.FindWrapper',
# options(
#   prefix='/usr/bin/head -c 10 {}'    # first ten bytes
#   suffix='/usr/bin/tail -c 10 {}'    # last ten bytes
#   mimetype='/usr/bin/file -b -i {}'  # mime type
#   season='s(?P<season>\\d{2})e(?P<episode>\\d{2})(?:  -  (?P<name>.*?))\.(?P<extension>[^.]{3,4})'
# )
class FindWrapper(ForeignDataWrapper):

  def __init__(self, options, columns):
    super(FindWrapper, self).__init__(options, columns)
    self._root = FindWrapper.__extract_root_directory(options)
    self._handlers = {}
    self._patterns = []
    FindWrapper.__init_handlers(self._handlers, self._patterns, options, columns)

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
    args = ['/usr/bin/find', '-O3', '-L', self._root,
            '-regextype', 'posix-egrep', '-ignore_readdir_race']

    # TODO: quals disabled until functionality complete
    for qual in quals:  # process quals to reduce raw find output
      if not qual.is_list_operator:  # Can't convert from array syntax to GNU find
        args += self._handlers[qual.field_name][2](qual) or EMPTY_LIST

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
        row[colname] = builtin_handlers[i][3](parts[i])

      matches = {}  # process patterns
      for i in range(0, len(patterns)):
        matches.update(patterns[i].fullmatch(parts[path_index]).groupdict())
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

  @staticmethod
  def __init_handlers(handlers, patterns, options, columns):
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
      elif value.find('(?P<') == -1:
        if value in BUILTINS:
          alias = BUILTINS[value]
          serializer = default_serializer if len(alias) < 3 else alias[2]
          handlers[option] = (0, alias[0], alias[1], serializer)
        else:
          log_to_postgres(logging.ERROR, 'Invalid alias: ' + value)
          return
      else:
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
        handler = BUILTINS[colname]
        serializer = default_serializer if len(handler) < 3 else handler[2]
        handlers[colname] = (0, handler[0], handler[1], serializer)
      elif colname == 'debug_quals':
        continue  # handle by name
      else:
        log_to_postgres(logging.ERROR, 'Invalid column: ' + colname)
        return


PATTERN_RE = re.compile('\(\?P<\s*([^ \)]+)\s*>')

EMPTY_LIST = []

def time_serialize(val):
  return val.replace('+', ' ')

def default_serializer(val):
  return val

def time_qual(name):
  def q(qual):
    if qual.operator == '=':
      return ['-%smin' % name, '0']
    elif qual.operator in ('<', '<='):
      return ['-not', '-newer%st' % name, qual.value]
    elif qual.operator in ('>', '>='):
      return ['-newer%st' % name, qual.value]
  return q

def num_qual(param):
  def q(qual):
    if qual.operator == '=':
      return [param, str(qual.value)]
  return q

def name_qual(qual):
  if qual.operator == '~~':     # LIKE
    return ['-name', qual.value.replace('%', '*')]
  elif qual.operator == '~~*':  # ILIKE
    return ['-iname', qual.value.replace('%', '*')]
  elif qual.operator == '!~~':
    return ['-not', '-name', qual.value.replace('%', '*')]
  elif qual.operator == '!~~*':
    return ['-not', '-iname', qual.value.replace('%', '*')]
  else:
    regex = qual.value
    if regex[0] == '^':
      regex = '(.+/)?' + regex[1]
    if qual.operator == '~':
      return ['-regex', qual.value]
    elif qual.operator == '~*':
      return ['-iregex', qual.value]
    elif qual.operator == '!~':
      return ['-not', '-regex', qual.value]
    elif qual.operator == '!~*':
      return ['-not', '-iregex', qual.value]

def depth_qual(qual):
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

def dir_qual(qual):
  if qual.operator == '~~':     # LIKE
    return ['-name', qual.value.replace('%', '*') + '/*']
  elif qual.operator == '~~*':  # ILIKE
    return ['-iname', qual.value.replace('%', '*') + '/*']
  elif qual.operator == '!~~':
    return ['-not', '-name', qual.value.replace('%', '*') + '/*']
  elif qual.operator == '!~~*':
    return ['-not', '-iname', qual.value.replace('%', '*') + '/*']

def fs_qual(name):
  if qual.operator == '=':
    return ['-fstype', qual.value]
  elif qual.operator == '!=':
    return ['-not', '-fstype', qual.value]

def hardlink_qual(qual):
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

def symlink_qual(qual):
  if qual.operator == '~~':
    return ['-lname', qual.value.replace('%', '*')]
  elif qual.operator == '~~*':
    return ['-ilname', qual.value.replace('%', '*')]
  elif qual.operator == '!~~':
    return ['-not', '-lname', qual.value.replace('%', '*')]
  elif qual.operator == '!~~*':
    return ['-not', '-ilname', qual.value.replace('%', '*')]

def path_qual(qual):
  if qual.operator == '~~':     # LIKE
    return ['-regex', qual.value.replace('%', '.*')]
  elif qual.operator == '~~*':  # ILIKE
    return ['-iregex', qual.value.replace('%', '.*')]
  elif qual.operator == '!~~':
    return ['-not', '-regex', qual.value.replace('%', '.*')]
  elif qual.operator == '!~~*':
    return ['-not', '-iregex', qual.value.replace('%', '.*')]
  elif qual.operator == '~':
    return ['-regex', qual.value]
  elif qual.operator == '~*':
    return ['-iregex', qual.value]
  elif qual.operator == '!~':
    return ['-not', '-regex', qual.value]
  elif qual.operator == '!~*':
    return ['-not', '-iregex', qual.value]

def type_qual(qual):
  if qual.operator == '=':
    return ['-type', qual.value[0]]

def owner_qual(param):
  def q(qual):
    if qual.operator == '=':
      return [param, qual.value]
  return q

def size_qual(qual):
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

def noop_qual(qual):
  return EMPTY_LIST

US = '\t'  # chr(31)

BUILTINS = {
  'accessed': ('%A+', time_qual('a'), time_serialize),
  'changed': ('%C+', time_qual('c'), time_serialize),
  'depth': ('%d', depth_qual),
  'dirname': ('%h', dir_qual),
  'eperms': ('%M', noop_qual),
  'filename': ('%f', name_qual),
  'filesystem': ('%F', fs_qual),
  'gid': ('%G', num_qual('-gid')),
  'group': ('%g', owner_qual('-group')),
  'hardlinks': ('%n', hardlink_qual),
  'inum': ('%i', num_qual('-inum')),
  'modified': ('%T+', time_qual('m'), time_serialize),
  'path': ('%P', path_qual),
  'perms': ('%m', noop_qual),
  'size': ('%s', size_qual),
  'symlink': ('%l', symlink_qual),
  'type': ('%Y', type_qual),
  'uid': ('%U', num_qual('-uid')),
  'user': ('%u', owner_qual('-user'))
  }
