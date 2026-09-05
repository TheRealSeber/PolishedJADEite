# PRECISION ACTION REQUIRED

## APPLET_API_DEPRECATED_FOR_REMOVAL -- REJECTED

Measured precision 0.4444 is below the effective threshold 0.7 (run-config).
- COMMENT_OR_STRING (10): Hits land inside string/comment literals; the pattern needs an anchor that excludes non-code text.

Counterexamples:
- src/jade/src/jade/AppletBoot.java:36 -- Javadoc prose, not a type reference: the token is either the ontology name 'DF-Applet' or the English word 'Applet' in a sentence, inside a comment that javac never compiles.
- src/jade/src/jade/domain/RemoteDFRequester.java:50 -- Javadoc prose, not a type reference: the token is either the ontology name 'DF-Applet' or the English word 'Applet' in a sentence, inside a comment that javac never compiles.
- src/jade/src/jade/domain/df.java:1139 -- Javadoc prose, not a type reference: the token is either the ontology name 'DF-Applet' or the English word 'Applet' in a sentence, inside a comment that javac never compiles.
- src/jade/src/jade/domain/df.java:1150 -- Javadoc prose, not a type reference: the token is either the ontology name 'DF-Applet' or the English word 'Applet' in a sentence, inside a comment that javac never compiles.
- src/jade/src/jade/domain/df.java:1163 -- Javadoc prose, not a type reference: the token is either the ontology name 'DF-Applet' or the English word 'Applet' in a sentence, inside a comment that javac never compiles.

## THREADGROUP_DESTROY_DEPRECATED_FOR_REMOVAL -- REJECTED

Measured precision 0.3333 is below the effective threshold 0.7 (run-config).
- NOT_THE_CONSTRUCT (2): The pattern describes a different syntactic construct than the rule; add left-hand-side context to the regex so it anchors on the real one.

Counterexamples:
- src/jade/src/jade/tools/applet/DFAppletCommunicator.java:145 -- Receiver 'a' is declared 'private Applet a' at DFAppletCommunicator.java:58, so this is java.applet.Applet.destroy(), a different method on a different class from ThreadGroup.destroy().
- src/jade/src/jade/tools/applet/DFAppletCommunicator.java:149 -- Receiver 'a' is declared 'private Applet a' at DFAppletCommunicator.java:58, so this is java.applet.Applet.destroy(), a different method on a different class from ThreadGroup.destroy().

