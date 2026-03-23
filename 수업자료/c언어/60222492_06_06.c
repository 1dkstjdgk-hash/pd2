#include <stdio.h>
void main(){
    int face,sour; 
	printf("연습생의 연기력과 가창력을 입력하시오: ");
	scanf("%d %d",&face,&sour);
	if(face>=80&&sour>=80)
	printf("만능 엔터테이너로서의 자질을 가지고 있습니다.");
	else if(face>=80)
	printf("배우로서의 자질을 가지고 있습니다.");
	else if(sour>=80)
	printf("가수로서의 자질을 가지고 있습니다.");
	else
	printf("연예인으로서의 자질이 없습니다");
}
