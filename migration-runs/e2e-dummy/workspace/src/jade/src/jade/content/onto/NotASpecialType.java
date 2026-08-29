package jade.content.onto;

//#APIDOC_EXCLUDE_FILE

public class NotASpecialType extends OntologyException {
// JADE-FLAG:DUMMY_TEST_RULE Dummy pattern HIGH

	public NotASpecialType() {
		super("");
	}
	
    public Throwable fillInStackTrace() {
        return this;
    }
}
