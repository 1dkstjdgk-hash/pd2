#include <stdio.h>
void main(){
	int num,w;
	printf("당신의 학번을 입력하시오:");
	scanf("%d",&num);
	printf("누구에게 투표하시겠습니까?(1~4번)");
	scanf("%d",&w);
	switch(w){
		 case 1:
		 
		 case 2:
		 	
		 case 3:
		 	
		 case 4: printf("%d학번 학생은 %d번 후보를 투표했습니다.",num,w);break;
		 	
		 default:printf("후보자 번호를 잘못 입력하셨습니다.");
	}
}
