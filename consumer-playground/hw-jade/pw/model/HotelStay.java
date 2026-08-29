package pw.model;

import java.io.Serializable;
import java.time.LocalDate;
import java.util.Objects;

public final class HotelStay implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String city;
    private final LocalDate fromDate;
    private final LocalDate toDate;
    private final int priceEur;

    public HotelStay(String city, LocalDate fromDate, LocalDate toDate, int priceEur) {
        this.city = city;
        this.fromDate = fromDate;
        this.toDate = toDate;
        this.priceEur = priceEur;
    }

    public String city() { return city; }
    public LocalDate fromDate() { return fromDate; }
    public LocalDate toDate() { return toDate; }
    public int priceEur() { return priceEur; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof HotelStay)) return false;
        HotelStay that = (HotelStay) o;
        return priceEur == that.priceEur
                && Objects.equals(city, that.city)
                && Objects.equals(fromDate, that.fromDate)
                && Objects.equals(toDate, that.toDate);
    }

    @Override
    public int hashCode() {
        return Objects.hash(city, fromDate, toDate, priceEur);
    }

    @Override
    public String toString() {
        return "HotelStay[city=" + city + ", fromDate=" + fromDate
                + ", toDate=" + toDate + ", priceEur=" + priceEur + "]";
    }
}