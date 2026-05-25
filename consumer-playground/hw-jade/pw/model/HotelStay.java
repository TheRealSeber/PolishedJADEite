package pw.model;

import java.io.Serializable;
import java.time.LocalDate;

public record HotelStay(
        String city,
        LocalDate fromDate,
        LocalDate toDate,
        int priceEur
) implements Serializable {
}