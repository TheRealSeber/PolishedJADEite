
## TRY_WITH_RESOURCES — behavioural delta in DFDBKB

`jade/domain/DFDBKB.java` previously closed its `Statement` in a `finally` block
and caught the close failure locally, printing a stack trace and letting the
method complete normally. Converting those sites to try-with-resources routes a
close failure to the enclosing `catch (SQLException e)` instead.

Concretely in `createTable`: a successful `CREATE TABLE` followed by a failed
`Statement.close()` now logs `SEVERE "Error creating table '<name>'"`, though
the table exists and the transaction committed. The same shape applies to
`dropTable`, `dropDFTables`, `tableExists` and `createIndices`.

The conversions are kept because they fix real descriptor leaks on the error
path, which was the point of the rule. What changed alongside that is where a
close failure surfaces — quieter before, louder and potentially misleading now.

A reviewer decides whether the DF's schema initialisation should report a close
failure as a table-creation failure. Suppressing it again would restore the old
behaviour at the cost of hiding the failure entirely, which is what the original
code did.
