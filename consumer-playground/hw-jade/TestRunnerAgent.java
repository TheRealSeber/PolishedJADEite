package pw.agents;

import jade.core.Agent;
import jade.core.behaviours.OneShotBehaviour;
import jade.wrapper.AgentController;
import pw.model.FlightRoute;
import pw.model.HotelStay;
import pw.model.TripRequest;

import java.time.LocalDate;
import java.util.List;

/**
 * Test runner for hw-jade consumer project.
 * Replicates the full ensemble from Main.java: 4 hotels, 3 flights,
 * 2 travel agencies, 1 customer. Waits for negotiation to complete,
 * then shuts down the platform gracefully.
 */
public class TestRunnerAgent extends Agent {

    @Override
    protected void setup() {
        System.out.println("=== HW-JADE Test Runner (full ensemble) ===");

        addBehaviour(new OneShotBehaviour() {
            @Override
            public void action() {
                try {
                    runTest();
                } catch (Exception e) {
                    System.err.println("HW_JADE_FAILED: " + e.getMessage());
                    e.printStackTrace(System.err);
                    System.exit(1);
                }
            }
        });
    }

    private void runTest() throws Exception {
        startHotel("HotelAgent1", HotelAgent.class,
                List.of(
                        new HotelStay("Tokyo", LocalDate.of(2026, 3, 3), LocalDate.of(2026, 3, 12), 200),
                        new HotelStay("Paris", LocalDate.of(2026, 3, 7), LocalDate.of(2026, 3, 9), 100)
                ), "TravelAgent1");

        startHotel("HotelAgent2", HotelAgent.class,
                List.of(
                        new HotelStay("Tokyo", LocalDate.of(2026, 3, 4), LocalDate.of(2026, 3, 12), 180),
                        new HotelStay("Rome", LocalDate.of(2026, 4, 10), LocalDate.of(2026, 4, 15), 140)
                ), "TravelAgent1");

        startHotel("HotelAgent3", HotelAgent.class,
                List.of(
                        new HotelStay("Tokyo", LocalDate.of(2026, 3, 3), LocalDate.of(2026, 3, 12), 100),
                        new HotelStay("Paris", LocalDate.of(2026, 3, 7), LocalDate.of(2026, 3, 9), 100)
                ), "TravelAgent2");

        startHotel("HotelAgent4", HotelAgent.class,
                List.of(
                        new HotelStay("Rome", LocalDate.of(2026, 4, 10), LocalDate.of(2026, 4, 15), 140)
                ), "TravelAgent2");

        startFlight("FlightAgent1", FlightAgent.class,
                List.of(
                        new FlightRoute("Warsaw", "Tokyo", LocalDate.of(2026, 3, 4), 500),
                        new FlightRoute("Tokyo", "Warsaw", LocalDate.of(2026, 3, 12), 600)
                ), "TravelAgent1");

        startFlight("FlightAgent2", FlightAgent.class,
                List.of(
                        new FlightRoute("Warsaw", "Tokyo", LocalDate.of(2026, 3, 4), 450),
                        new FlightRoute("Tokyo", "Warsaw", LocalDate.of(2026, 3, 12), 650)
                ), "TravelAgent1");

        startFlight("FlightAgent3", FlightAgent.class,
                List.of(
                        new FlightRoute("Warsaw", "Tokyo", LocalDate.of(2026, 3, 4), 700),
                        new FlightRoute("Tokyo", "Warsaw", LocalDate.of(2026, 3, 12), 600)
                ), "TravelAgent2");

        startTravelAgency("TravelAgent1", TravelAgencyAgent.class,
                200,
                List.of("HotelAgent1", "HotelAgent2"),
                List.of("FlightAgent1", "FlightAgent2"));

        startTravelAgency("TravelAgent2", TravelAgencyAgent.class,
                150,
                List.of("HotelAgent3", "HotelAgent4"),
                List.of("FlightAgent3"));

        Thread.sleep(1000);

        TripRequest request = new TripRequest(
                "Warsaw", "Tokyo",
                LocalDate.of(2026, 3, 4),
                LocalDate.of(2026, 3, 12)
        );
        createAndStart("CustomerAgent", CustomerAgent.class.getName(),
                new Object[]{request});

        // Wait for full FIPA ContractNet negotiation to complete
        // (CFP → proposals → selection → payment → confirmation)
        try {
            Thread.sleep(15000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }

        System.out.println("[TestRunner] Scenario complete. Shutting down.");
        System.exit(0);
    }

    private void createAndStart(String name, String className, Object[] args) throws Exception {
        AgentController c = getContainerController().createNewAgent(name, className, args);
        c.start();
    }

    private void startHotel(String name, Class<?> cls, List<HotelStay> catalog, String owner) throws Exception {
        createAndStart(name, cls.getName(), new Object[]{catalog, owner});
    }

    private void startFlight(String name, Class<?> cls, List<FlightRoute> catalog, String owner) throws Exception {
        createAndStart(name, cls.getName(), new Object[]{catalog, owner});
    }

    private void startTravelAgency(String name, Class<?> cls, int fee,
                                   List<String> hotels, List<String> flights) throws Exception {
        createAndStart(name, cls.getName(), new Object[]{fee, hotels, flights});
    }
}
