package jade.core.sam;

public class MediatedMeasureProvider extends AverageMeasureProviderImpl {
// JADE-FLAG:DUMMY_TEST_RULE Dummy pattern HIGH
	
	private MeasureProvider realProvider; 
	
	public MediatedMeasureProvider(MeasureProvider realProvider) {
		this.realProvider = realProvider;
	}
	
	void collectNewValue() {
		Number v = realProvider.getValue();
		if (v != null && !Double.isNaN(v.doubleValue())) {
			addSample(realProvider.getValue());
		}
	}
}
