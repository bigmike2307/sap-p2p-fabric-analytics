@AbapCatalog.viewEnhancementCategory: [#NONE]
@AccessControl.authorizationCheck: #NOT_REQUIRED
@EndUserText.label: 'P2P extraction: purchase requisition item'
@Metadata.ignorePropagatedAnnotations: true
@ObjectModel.usageType: { serviceQuality: #D, sizeCategory: #L, dataClass: #TRANSACTIONAL }
@Analytics.dataCategory: #FACT
@Analytics.dataExtraction.enabled: true
@Analytics.dataExtraction.delta.changeDataCapture.automatic: true
define view entity ZX_P2P_EBAN
  as select from eban
{
  key banfn,
  key bnfpo,
      bsart,
      loekz,
      statu,
      ekgrp,
      afnam,
      txz01,
      matnr,
      werks,
      matkl,
      @Semantics.quantity.unitOfMeasure: 'meins'
      menge,
      meins,
      badat,
      frgdt,
      lfdat,
      @Semantics.amount.currencyCode: 'waers'
      preis,
      peinh,
      waers,
      knttp,
      ebeln,
      ebelp
}
