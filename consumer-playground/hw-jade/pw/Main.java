package pw;

import jade.core.Profile;
import jade.core.ProfileImpl;
import jade.core.Runtime;
import jade.wrapper.AgentContainer;
import jade.wrapper.AgentController;
import pw.agents.CustomerAgent;
import pw.agents.FlightAgent;
import pw.agents.HotelAgent;
import pw.agents.TravelAgencyAgent;
import pw.model.FlightRoute;
import pw.model.HotelStay;
import pw.model.TripRequest;

import java.time.LocalDate;
import java.util.List;

public class Main {
    public static void main(String[] args) throws Exception {
        System.out.println("[MAIN] Starting JADE travel scenario...");

        AgentContainer container = getAgentContainer();
        System.out.println("[MAIN] JADE container created on 127.0.0.1:12000");

        List<HotelStay> hotel1Catalog = List.of(
                new HotelStay("Tokyo", LocalDate.of(2026, 3, 3), LocalDate.of(2026, 3, 12), 200),
                new HotelStay("Paris", LocalDate.of(2026, 3, 7), LocalDate.of(2026, 3, 9), 100)
        );
        List<HotelStay> hotel2Catalog = List.of(
                new HotelStay("Tokyo", LocalDate.of(2026, 3, 4), LocalDate.of(2026, 3, 12), 180),
                new HotelStay("Rome", LocalDate.of(2026, 4, 10), LocalDate.of(2026, 4, 15), 140)
        );
        List<HotelStay> hotel3Catalog = List.of(
                new HotelStay("Tokyo", LocalDate.of(2026, 3, 3), LocalDate.of(2026, 3, 12), 100),
                new HotelStay("Paris", LocalDate.of(2026, 3, 7), LocalDate.of(2026, 3, 9), 100)
        );
        List<HotelStay> hotel4Catalog = List.of(
                new HotelStay("Rome", LocalDate.of(2026, 4, 10), LocalDate.of(2026, 4, 15), 140)
        );

        List<FlightRoute> flight1Catalog = List.of(
                new FlightRoute("Warsaw", "Tokyo", LocalDate.of(2026, 3, 4), 500),
                new FlightRoute("Tokyo", "Warsaw", LocalDate.of(2026, 3, 12), 600)
        );
        List<FlightRoute> flight2Catalog = List.of(
                new FlightRoute("Warsaw", "Tokyo", LocalDate.of(2026, 3, 4), 450),
                new FlightRoute("Tokyo", "Warsaw", LocalDate.of(2026, 3, 12), 650)
        );
        List<FlightRoute> flight3Catalog = List.of(
                new FlightRoute("Warsaw", "Tokyo", LocalDate.of(2026, 3, 4), 700),
                new FlightRoute("Tokyo", "Warsaw", LocalDate.of(2026, 3, 12), 600)
        );

        start(container, "HotelAgent1", HotelAgent.class.getName(), new Object[]{hotel1Catalog, "TravelAgent1"});
        start(container, "HotelAgent2", HotelAgent.class.getName(), new Object[]{hotel2Catalog, "TravelAgent1"});
        start(container, "HotelAgent3", HotelAgent.class.getName(), new Object[]{hotel3Catalog, "TravelAgent2"});
        start(container, "HotelAgent4", HotelAgent.class.getName(), new Object[]{hotel4Catalog, "TravelAgent2"});

        start(container, "FlightAgent1", FlightAgent.class.getName(), new Object[]{flight1Catalog, "TravelAgent1"});
        start(container, "FlightAgent2", FlightAgent.class.getName(), new Object[]{flight2Catalog, "TravelAgent1"});
        start(container, "FlightAgent3", FlightAgent.class.getName(), new Object[]{flight3Catalog, "TravelAgent2"});

        start(
                container,
                "TravelAgent1",
                TravelAgencyAgent.class.getName(),
                new Object[]{
                        200,
                        List.of("HotelAgent1", "HotelAgent2"),
                        List.of("FlightAgent1", "FlightAgent2")
                }
        );
        start(
                container,
                "TravelAgent2",
                TravelAgencyAgent.class.getName(),
                new Object[]{
                        150,
                        List.of("HotelAgent3", "HotelAgent4"),
                        List.of("FlightAgent3")
                }
        );

        Thread.sleep(1_000);

        TripRequest request = new TripRequest(
                "Warsaw",
                "Tokyo",
                LocalDate.of(2026, 3, 4),
                LocalDate.of(2026, 3, 12)
        );
        start(container, "CustomerAgent", CustomerAgent.class.getName(), new Object[]{request});
    }

    private static AgentContainer getAgentContainer() {
        Runtime runtime = Runtime.instance();
        Profile profile = new ProfileImpl();
        profile.setParameter(Profile.GUI, "false");
        profile.setParameter(Profile.LOCAL_HOST, "127.0.0.1");
        profile.setParameter(Profile.MAIN_PORT, "12000");
        profile.setParameter("local-port", "12001");

        AgentContainer container;
        try {
            container = runtime.createMainContainer(profile);
        } catch (Exception e) {
            throw new IllegalStateException("Failed to start JADE main container. Check if ports 12000/12001 are free.", e);
        }
        if (container == null) {
            throw new IllegalStateException("JADE main container is null. Check JADE runtime logs for port binding errors.");
        }
        return container;
    }

    private static void start(AgentContainer container, String name, String className, Object[] args) throws Exception {
        AgentController controller = container.createNewAgent(name, className, args);
        controller.start();
    }
}
