# - Find MySQL
# Find the native MySQL includes and library
# http://www.cmake.org/Wiki/CMakeUserFindMySQL
# Slightly modified
#
#   MYSQL_FOUND        - True if MySQL found.
#   MYSQL_INCLUDE_DIRS - where to find mysql.h, etc.
#   MYSQL_LIBRARIES    - List of libraries when using MySQL.
#

# we need to find the dynamic library here; it seems to be
# mysqlclient on Linux, but libmysql on Windows ...
# Debian/MariaDB ships libmariadb (+ mysql.h under mariadb/ or mysql/).
IF( WIN32 )
  LIST( APPEND MYSQL_NAMES "libmariadb" )
ELSE( WIN32 )
  LIST( APPEND MYSQL_NAMES "mariadb" "libmariadb" "mysqlclient_r" "mysqlclient" )
ENDIF( WIN32 )

FIND_PATH(
  MYSQL_INCLUDE_DIRS "mysql.h"
  PATH_SUFFIXES "mysql" "mariadb"
  PATHS
    /usr/include
    /usr/include/mysql
    /usr/include/mariadb
    /usr/local/include
  )
FIND_LIBRARY(
  MYSQL_LIBRARIES
  NAMES ${MYSQL_NAMES}
  PATHS
    /usr/lib
    /usr/lib/x86_64-linux-gnu
    /usr/local/lib
  )
MARK_AS_ADVANCED(
  MYSQL_INCLUDE_DIRS
  MYSQL_LIBRARIES
  )

# handle the QUIETLY and REQUIRED arguments and set MYSQL_FOUND to TRUE if
# all listed variables are TRUE
INCLUDE( "FindPackageHandleStandardArgs" )
FIND_PACKAGE_HANDLE_STANDARD_ARGS(
  "MySQL"
  DEFAULT_MSG
  MYSQL_LIBRARIES
  MYSQL_INCLUDE_DIRS
  )
