package pw.model;

import java.io.Serializable;
import java.time.LocalDate;

public record FlightRoute(
        String fromCity,
        String toCity,
        LocalDate date,
        int priceEur
) implements Serializable {
}