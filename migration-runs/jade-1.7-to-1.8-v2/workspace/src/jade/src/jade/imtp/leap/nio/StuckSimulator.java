package jade.imtp.leap.nio;

//#J2ME_EXCLUDE_FILE

// Class used for debugging purpose only
class StuckSimulator {
	
	private static Object lock = new Object();
	
	static void init() {
		Thread t = new Thread() {
// JADE-FLAG:LAMBDA_CONVERSION Anonymous classes with a single method can be converted to lambda expressions (SAM conversion) as introduced by JEP 126. 0.8
			public void run() {
				synchronized (lock) {
					System.err.println("LOCK acquired");
					try {
// JADE-MODERNIZATION-DEFERRED:TRY_WITH_RESOURCES Extremely broad pattern (1832 flags), deferred for targeted future review
						while (true) {
							Thread.sleep(10000);
						}
					}
					catch (Exception e) {
						e.printStackTrace();
					}
				}
				System.err.println("LOCK released");
			}
		};
		t.start();
	}
	
	static void stuck() {
		System.err.println("Thread "+Thread.currentThread().getName()+" STUCK!!!!");
		synchronized (lock) {
			System.err.println("THIS IS IMPOSSIBLE!!!!!!!!!!!!");
		}
	}

}
