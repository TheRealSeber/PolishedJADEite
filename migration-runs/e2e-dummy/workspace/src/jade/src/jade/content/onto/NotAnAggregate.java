package jade.content.onto;

//#APIDOC_EXCLUDE_FILE

public class NotAnAggregate extends OntologyException {
// JADE-FLAG:DUMMY_TEST_RULE Dummy pattern HIGH

	public NotAnAggregate() {
		super("");
	}
	
	public Throwable fillInStackTrace() {
		return this;
	}
}
