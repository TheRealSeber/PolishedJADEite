package pw.model;

import java.io.Serializable;

public record HotelProposal(
        String providerName,
        int priceEur
) implements Serializable {
}