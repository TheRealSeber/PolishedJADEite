package jade.core;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

//#PJAVA_EXCLUDE_FILE
//#MIDP_EXCLUDE_FILE

@Retention(RetentionPolicy.RUNTIME)
// JADE-FLAG:STRICTER_CAST_CHECKING Java 6 enforces stricter cast rules. Complex casts should be reviewed. 0.8
public @interface Restore {
	String DEFAULT_RESTORE = "_DEFAULT_";
	
	boolean skip() default false;
	String method() default DEFAULT_RESTORE;
}
