package jade.content.onto;

public class UnknownSlotException extends OntologyException {
// JADE-FLAG:DUMMY_TEST_RULE Dummy pattern HIGH

	public UnknownSlotException() {
		super(null);
	}
	
	public UnknownSlotException(String slotName) {
		super("Slot "+slotName+" does not exist");
	}
}
